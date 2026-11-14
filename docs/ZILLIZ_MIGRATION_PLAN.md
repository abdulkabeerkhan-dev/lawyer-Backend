# Zilliz Cloud migration: ingestion spec and relevance plan

Status: proposed, 2026-11-14. Executor: Antigravity. Reviewer: Claude Code.
Pinecone (`legal-kb-pk-local`) is abandoned: the vendor-issued key returns 401 and the account is not accessible.

> Rule zero: **build the full pipeline, run it on 1,000 cases, pass the validation gates in §9, then run the rest.** Never upsert the full corpus in one untested pass.

---

## 1. Source data (audited 2026-11-14)

Use **only** these 10 files in the root of `I:\`:

| File | Rows | Notes |
|---|---|---|
| `PLD_cases.csv` | 23,962 | 18.3k rows contain the full reported judgment. Page numbers repeat across courts. 434 error pages. |
| `MLD_cases.csv` | 18,975 | ~10k full judgments; 1,226 duplicate rows; 239 error pages |
| `SCMR_cases.csv` | 18,756 | ~5.2k full judgments; 1,019 duplicate rows |
| `YLR_cases.csv` | 18,854 | ~5.7k full judgments |
| `PCRLJ_cases.csv` | 26,737 | Headnote + site navigation chrome; single `Judgment Content` column |
| `CLC_cases.csv` | 20,229 | mostly headnotes |
| `PLC_cases.csv` | 8,784 | mostly headnotes |
| `CLD_cases.csv` | 5,333 | headnotes |
| `PTD_cases.csv` | 3,185 | single `Judgment Content` column, nav chrome |
| `GBLR_cases.csv` | 341 | mostly full judgments |

**Exclude:**
- `I:\pakistan_law_cases.csv` (915,853 rows; 842,684 duplicates; content is "Server Error" pages).
- Copies elsewhere (`I:\chrome_profile\PLD_cases.csv`, `I:\GoPro\PLD_cases.csv`, anything under `I:\Downloads`). Record the sha256 of each file actually ingested in the run manifest.

Totals: 145,156 rows → **141,342 unique cases** after the keying rules below. ~291M tokens of text before cleaning.

### Column semantics (counter-intuitive, verified)
- Layout A (SCMR, PLD, MLD, YLR, CLC, PLC, CLD, GBLR): `Headnotes / Case Description` often holds the **full reported judgment** (starts e.g. `2021 S C M R 1466 [Supreme Court of Pakistan] Present: ...`). `Full Judgment Body` usually holds the **catchword headnote** (`S. 497---Bail---...`). Do not trust the names; classify by content (§3).
- Layout B (PCRLJ, PTD): one `Judgment Content` column, prefixed by site chrome (`My Account Feedback Customer Care Office PLD Publishers ...`).
- `Journal` column is unreliable (77 rows disagree with the citation, e.g. a `PCrLJ` row holding `2026 CLC 12`). **Always parse the citation from `Citation / Title`.**
- `Citation / Title` format: `{index}\t{YYYY JOURNAL PAGE}\t{Parties} - {Judge} - {Counsel}\t{COURT-CODE-STRING}`.

---

## 2. Canonical case key (dedupe layer 1)

```
case_key = f"{year}_{journal}_{court_code}_{page}"     e.g. 2024_PLD_SC_1, 2024_SCMR_SC_14
```

- **Court must be in the key.** 3,711 citations are shared by different courts (`2024 PLD 1` exists for SC, FSC, LHC, SHC, PHC, BHC, IHC and AJK HC). The existing Turso `case_id` (`2024_PLD_1`) merges these. Do not reuse it as a key; store it as `legacy_case_id`.
- `journal` normalisation: `PCrLJ`/`P.Cr.L.J` → `PCRLJ`; `PLC(CS)` stays distinct from `PLC`.
- `court_code` from the last tab-field of `Citation / Title`:

| Header string | court_code | court_level |
|---|---|---|
| SUPREME-COURT | SC | 1 |
| FEDERAL-SHARIAT-COURT | FSC | 2 |
| LAHORE-HIGH-COURT-LAHORE (and benches) | LHC | 3 |
| KARACHI-HIGH-COURT-SINDH | SHC | 3 |
| PESHAWAR-HIGH-COURT | PHC | 3 |
| QUETTA-HIGH-COURT-BALOCHISTAN | BHC | 3 |
| ISLAMABAD | IHC | 3 |
| HIGH-COURT-AZAD-KASHMIR | AJKHC | 3 |
| SUPREME-APPELLATE-COURT (GB) | GBSAC | 3 |
| anything else | log it, `OTHER`, level 4 | 4 |

  Unknown strings go to a review log. Never guess.
- **Duplicate rows of the same `case_key`** (2,877): keep one. Order of preference: (1) not junk, (2) contains a full judgment, (3) longest cleaned text, (4) latest `Scraped At`.
- Rows with no parsable citation (284): log, do not ingest.

## 3. Text extraction and cleaning

Per row, consider every text column and classify each:
- `junk`: starts with/contains `Server Error in`, `Error Code:700`, `Something went wrong`, or is shorter than 200 chars after cleaning.
- `full_judgment`: contains bench markers (`Present:` / `Before ... J` / `JJ`), a case number (`... No. ... of YYYY`), and is ≥ 6,000 chars.
- `headnote`: catchword format (`S. 497---`, `---Bail---`, `Ss. 302/34`) or anything else non-junk.

Output per case: `headnote_text` (may be empty), `judgment_text` (may be empty), `content_level ∈ {full_judgment, headnote_only}`.

Cleaning (apply to both): strip site chrome (`My Account Feedback ... Customer Care ...` block), `Citation Name: ...`, `Bookmark this Case`, `Copyrights © ...`, `This site is developed & maintained ...`, `Help FAQ's Sitemap`, HTML tags, NBSP; collapse whitespace. Reuse `core/hierarchical_legal_chunker.py::clean_portal_debris` and extend it; do not write a second cleaner.

### Parallel reports (dedupe layer 2)
The same judgment can be reported in two journals (e.g. SCMR and PLD). Compute `text_hash = sha1(normalised first 3,000 chars of judgment_text or headnote_text)`. If two case_keys share a `text_hash`, keep the one with the higher-authority journal (SCMR/PLD over others), embed it once, and store the other citations in `parallel_citations`. Do not embed the duplicate. (19 found by a quick probe; expect more after full normalisation.)

## 4. Segmentation (dedupe layer 3)

Never use fixed sliding windows across sections (the old `batch_vector_indexer.py` did 512-token windows + 64 overlap; that is the "blind chunking" problem in `LEGAL_RAG_FAILURE_ANALYSIS.md`).

**Headnote**: split into catchword blocks. A new block starts at a statute/provision catchword (`S. 497---`, `Ss. 302/34---`, `O. XXXIX, R. 1---`, `Art. 199---`) or a blank-line boundary. One block = one legal proposition = one chunk (`section = "headnote"`). Merge blocks < 40 tokens with the next.

**Judgment body**: use `core/structural_judgment_segmenter.py` / `HierarchicalLegalChunker.parse_judgment_sections` to label paragraphs as `facts | arguments | issues | reasoning | holding | order`. Pack whole paragraphs into chunks of **300–500 tokens** without crossing a section boundary. Split a paragraph only if it alone exceeds 500 tokens (sentence boundaries). No overlap needed with a contextual embedding model; otherwise one-paragraph overlap.

**Chunk identity** (deterministic, never auto-generated):
```
chunk_id = f"{case_key}:{section}:{ordinal:03d}"     e.g. 2024_SCMR_SC_14:headnote:002
chunk_hash = sha1(chunk_text)
```
- Within a case, drop a chunk whose normalised text equals another chunk of the same case (headnotes are often repeated inside the body).
- Drop chunks that are < 25 tokens after cleaning.

## 5. Metadata per chunk

| Field | Source | Use |
|---|---|---|
| `case_key`, `citation`, `parallel_citations[]`, `legacy_case_id` | §2–3 | grouping, display, mapping to Turso |
| `journal`, `year`, `court_code`, `court_level` | §2 | filters, authority prior |
| `parties`, `judge` | `Citation / Title` | display |
| `section` | §4 | prefer `headnote`/`reasoning`/`holding` |
| `content_level` | §3 | never present a headnote as a judgment |
| `statutes[]` | catchwords, e.g. `Criminal Procedure Code (Cr.P.C) 1898--497` → `CRPC_1898_SEC_497`; also `S. 489-F PPC` patterns. Canonical IDs as in `data/statutes_v2`. | filter + boost |
| `domain` | rules from statutes (PPC/CrPC/CNSA → criminal; CPC/SRA/TPA → civil; FIO → banking; MFLO/Family Courts → family; PRPA/SRPO → rent; Art. 199/184 → constitutional; service statutes → service; tax statutes → tax). Multi-valued allowed; first = primary. | partition key / filter |
| `cited_by_count` | citation graph: count of *other* cases whose text cites this citation (regex over all judgment_text) | authority prior (§10) |
| `chunk_hash`, `embed_model`, `schema_version`, `ingested_at` | pipeline | idempotency, audits |

## 6. Embedding

1. **Bake-off first (≈ $1–3).** Embed a 2,000-case sample that includes the golden-set authorities with each candidate, then compare Recall@10 / MRR on the golden set (§10):
   - `voyage-law-2` (current, legal-domain, 1024-d, $0.12/M)
   - `voyage-4-large` ($0.12/M)
   - `voyage-context-4` ($0.12/M) — contextualised chunk embeddings: each chunk is embedded with its whole judgment as context, which suits segmented judgments.
   Prices from the Voyage pricing page saved 2026-10-03 (`docs/voyage_pricing_20261003.html`); re-check model limits (max tokens per document/request, output dimensions) in the current Voyage docs before coding.
2. Documents use `input_type="document"`; queries use the **same model** with `input_type="query"`.
3. For non-contextual models, prefix every chunk with a context header:
   `[2024 SCMR 14 | Supreme Court | Criminal | CrPC s.497 | headnote]`
4. Full run: ~250–290M tokens → **≈ $30–35** at $0.12/M. Batch to the documented per-request token limit; retry with exponential backoff on 429/5xx; never re-embed a chunk whose `chunk_hash` + `embed_model` is already in the manifest.

## 7. Zilliz collection

One collection, `judgments_v1`. Explicit schema, **`auto_id=False`**, no dynamic fields.

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | VARCHAR(128), primary key | §4 |
| `case_key` | VARCHAR(64) | scalar index; used for `group_by` |
| `text` | VARCHAR(65535), `enable_analyzer=True` | chunk text incl. context header; input to BM25 function |
| `dense` | FLOAT_VECTOR(dim from bake-off) | index AUTOINDEX, metric COSINE |
| `sparse` | SPARSE_FLOAT_VECTOR | output of a **BM25 function** on `text` (in-engine full-text search), index SPARSE_INVERTED_INDEX, metric BM25 |
| `citation`, `journal`, `court_code` | VARCHAR | filters/display |
| `year`, `court_level`, `cited_by_count` | INT | filters/ranking |
| `section`, `content_level` | VARCHAR | filters |
| `domain` | VARCHAR, **partition key** | speeds domain-filtered search |
| `statutes` | ARRAY<VARCHAR>(max 64) | `array_contains_any` filters |
| `chunk_hash`, `embed_model`, `schema_version` | VARCHAR | audits |

Verify against the current Zilliz Cloud docs that your cluster tier supports: BM25 function / full-text search, partition key, `ARRAY` fields, `group_by_field` in search, and `hybrid_search` with RRF. If the tier lacks the BM25 function, keep keyword search on Turso FTS (already live, `legal_ai/retrieval/turso_fts_index.py`) and store only dense vectors.

Sizing: ~0.8–1.0M chunks × 1024-d float ≈ 3.5–4 GB of vectors plus text and sparse index. Choose the tier/CU accordingly; if cost matters, test 512-d output (if the chosen model supports reduced dimensions) in the bake-off.

## 8. Upsert protocol (dedupe layer 4)

- Write all records with `upsert` keyed on `chunk_id`. Re-running any batch overwrites; it never duplicates.
- **Run manifest** (Turso table `vector_ingest_manifest` or a local SQLite file checked into nothing): `chunk_id, case_key, chunk_hash, embed_model, collection, status, batch_id, upserted_at, source_file_sha256`. Skip chunks already `done` with the same `chunk_hash` + `embed_model`.
- **Re-segmenting a case**: before upserting its new chunks, delete by `case_key == X` and `chunk_id not in new_ids`, so stale chunks from a previous segmentation cannot linger.
- Batches of whole cases (never split one case across batches). Checkpoint after every batch; the job must be resumable after a crash with no duplicates.
- Credentials (`ZILLIZ_URI`, `ZILLIZ_TOKEN`, `VOYAGE_API_KEY`) from `.env` only. Never paste them into chat or commit them.

## 9. Validation gates

Run after the 1,000-case pilot and after the full load. All must pass.

1. `count(collection)` == manifest rows with `status=done`.
2. No primary-key duplicates (export `chunk_id`s, compare unique count).
3. Every ingested `case_key` has ≥ 1 chunk; no chunk's `case_key` prefix differs from its `chunk_id` prefix.
4. No two `case_key`s share a `text_hash` (parallel reports collapsed).
5. Zero chunks containing boilerplate markers (`Bookmark this Case`, `Oratier`, `My Account Feedback`, `Server Error`).
6. Spot check 20 random cases: chunk texts concatenated ≈ cleaned source text; sections labelled sensibly.
7. Golden-set retrieval (§10) on the pilot meets or beats the Turso-FTS baseline.

## 10. Relevance plan (backend, after the load)

Measured problems: Pinecone dead in production (401 swallowed), keyword search over 7% of the corpus (fixed 2026-11-11), headnote-only text, merged PLD cases, and recency-first staging in `main.py` (Lane A searches 2026–2024 first and only widens if "insufficient", which favours recent cases over leading authorities).

In order of expected impact:
1. **Golden set** (`eval/golden_qa.json`): 60–100 lawyer-verified queries with must-retrieve citations and must-not-appear items. Every change below is accepted only if Recall@10 / MRR improve. Seed with the 302-bail and 489-F queries (2024 SCMR 14, 2025 SCMR 129, 2010 SCMR 806, 2023 SCMR 2122, 2023 SCMR 1948).
2. **Hybrid search in Zilliz**: dense + BM25 `hybrid_search` with RRF, `group_by_field="case_key"` so the top-k are distinct cases, not ten chunks of one case.
3. **Planner → filters**: the query planner already extracts domain and provisions. Run (a) filtered (`domain == X and array_contains_any(statutes, [...])`) and (b) unfiltered; merge. Hard filters alone miss mis-tagged cases.
4. **Authority prior**: final score = relevance × f(`court_level`, `cited_by_count`). Leading authorities such as Salman Mushtaq (2024 SCMR 14) are cited by many later bail orders; that is how a lawyer would rank them too.
5. **Rerank** the top ~50 cases with a cross-encoder / Voyage reranker on (query, best 2 chunks per case).
6. **Revisit recency staging**: rank on relevance + authority first; use recency as a tie-breaker or an explicit user filter.
7. **Answer from full text**: when `content_level=full_judgment`, give the model the `reasoning`/`holding` chunks, not the catchword headnote.

## 11. Turso must match

Vectors point to `case_key`; the app shows text from Turso. Load the same canonical registry into a new Turso table `cases_v2` (`case_key` PK, clean `headnote_text`, `judgment_text`, metadata, `legacy_case_id`), rebuild FTS on it, and switch reads after validation. The old `case_texts` stays until cut-over (it has merged PLD cases and 91% headnote-only rows).

## 12. Backend switch

- New `legal_ai/retrieval/zilliz_search.py` with the same return shape as `pinecone_search.py`; config `VECTOR_BACKEND=zilliz`.
- Query embedding with the bake-off model, `input_type="query"`.
- `/health` probe for Zilliz (same pattern as the Pinecone probe in `main.py`).
- Remove the Pinecone path once Zilliz passes the golden set.

## 13. Do not

- Do not use `auto_id`, random UUIDs, or row indexes as IDs.
- Do not ingest `pakistan_law_cases.csv` or file copies outside `I:\` root.
- Do not key PLD cases without the court.
- Do not trust the `Journal` column or the column names; classify by content.
- Do not overwrite Turso `case_texts` in place.
- Do not run the full load before the pilot passes §9.
