# Task: build and run the Zilliz Cloud ingestion pipeline for Pakistani case law

## Context
This is the backend of a legal research assistant for Pakistani lawyers (`d:\lawyer-Backend`). Its vector database (Pinecone) is no longer accessible, and search relevance has been poor. We are moving the judgment vectors to **Zilliz Cloud**, rebuilding them from the original scraped CSVs with proper deduplication and structural segmentation, and embedding them with **Voyage AI**.

Read these before starting:
1. `docs/antigravity/RULES.md`: hard rules. Follow them at all times.
2. `docs/ZILLIZ_MIGRATION_PLAN.md`: the full specification (source files, column semantics, keys, cleaning, segmentation, metadata, schema, upsert protocol, validation gates). It is based on an audit of the actual data; its numbers are your baseline.
3. `core/hierarchical_legal_chunker.py` and `core/structural_judgment_segmenter.py`: existing cleaning/segmentation code to reuse.
4. `data/statutes_v2/*.json`: canonical statute IDs (e.g. `CRPC_1898_SEC_497`) for tagging chunks.

## Goal
A Zilliz collection `judgments_v1` holding every unique case from the 10 journal CSVs, segmented into headnote blocks and judgment sections, with deterministic IDs, rich metadata and Voyage embeddings. There must be **no duplicates**, it must be resumable, and it must be verified by the validation gates. A matching registry goes into a new Turso table `cases_v2`.

## Phases
Work on branch `zilliz-ingest`. Write code in `scripts/zilliz/`, tests in `tests/zilliz/`, and outputs in `I:\zilliz_work\`. At each **STOP**, post the report described and wait for "approved, continue".

### Phase 0: Preflight
- Confirm `ZILLIZ_URI`, `ZILLIZ_TOKEN`, `VOYAGE_API_KEY` and Turso variables exist in `.env` (report present/missing only, never values).
- Connect to Zilliz and report the cluster tier and version. From the **current Zilliz docs**, confirm whether our tier supports: the BM25 function (full-text search), partition key, ARRAY fields, `group_by_field` in search, and `hybrid_search` with RRF.
- From the **current Voyage docs**, record for `voyage-law-2`, `voyage-4-large` and `voyage-context-4`: output dimensions, max tokens per input/document, max tokens and items per request, and price.
- Compute the sha256 and row count of each of the 10 source CSVs.

**STOP 0.** Report: env check, tier capabilities (with doc links), Voyage limits table, file hashes and row counts.

### Phase 1: Case registry (spec §1–3)
Build `scripts/zilliz/build_registry.py`:
- Parse `Citation / Title` into citation, year, journal, page, parties, judge and court string. Map the court string to `court_code`/`court_level` (spec §2 table); log unknown strings.
- Classify every text column of each row as junk / full_judgment / headnote (spec §3) and clean it.
- Build `case_key`, collapse duplicate rows (preference order in spec §2), and detect parallel reports by `text_hash`.
- Output `I:\zilliz_work\registry.jsonl` (one line per case) and `registry_report.json`.
- Unit tests: citation parsing (including `PCrLJ`, `PLC(CS)`, PLD court variants), court mapping, junk detection, duplicate preference, case_key determinism.

**STOP 1.** Report: rows read per file; unique cases (expected ≈ 141,342); duplicate rows collapsed (≈ 2,877); junk rows (≈ 653+); rows without a citation (≈ 284); cross-court citations kept distinct (≈ 3,711); parallel-report pairs; unknown court strings with counts; full_judgment vs headnote_only counts per journal (expected ≈ 39.6k full judgments in total). Include 5 random registry entries (text truncated to 300 chars).

### Phase 2: Segmentation and metadata (spec §4–5)
Build `scripts/zilliz/segment.py` and `scripts/zilliz/enrich.py`:
- Split headnotes into catchword blocks, and judgments into labelled sections packed into 300–500-token chunks. Use deterministic `chunk_id`s and `chunk_hash`, and drop within-case duplicates and tiny chunks.
- Tag `statutes[]` with canonical IDs, `domain`, `court_level`, and `cited_by_count` from a citation graph over all judgment text.
- Output `I:\zilliz_work\chunks.jsonl`.
- Unit tests: identical input gives identical chunk_ids; no chunk crosses a section boundary; statute tagging on 10 hand-written catchword samples; dedupe of a headnote repeated in the body.

**STOP 2.** Report: total chunks; chunks per section type; token distribution (p10/p50/p90/max); total tokens and estimated embedding cost per candidate model; top 20 statutes and the domain distribution; the top 20 cases by `cited_by_count` (sanity check: these should be well-known leading cases); 3 fully segmented example cases (one SC full judgment, one HC full judgment, one headnote-only).

### Phase 3: Embedding bake-off (spec §6), spend ≤ $5
- Pick a 2,000-case sample that includes every case cited in `eval/golden_qa.json` plus these verified authorities: `2024 SCMR 14`, `2025 SCMR 129`, `2010 SCMR 806`, `2023 SCMR 2122`, `2023 SCMR 1948`.
- Embed the sample with `voyage-law-2`, `voyage-4-large` and `voyage-context-4` into a scratch collection per model, or locally with brute-force cosine.
- Evaluate Recall@10, Recall@50 and MRR at case level on every golden-set query, plus these two:
  - "My client was arrested under Section 302 PPC for murder. What are the grounds for post-arrest bail and the procedure?"
  - "A cheque was dishonoured for insufficient funds. Is Section 489-F PPC attracted, what is the procedure, and what are the ingredients of the offence?"
- If the golden set has fewer than 20 queries, say so in the report; do not invent expected answers.

**STOP 3.** Report: a metrics table per model, cost spent, the top 10 cases for the two queries above per model, and your recommendation with reasons. The user picks the model.

### Phase 4: Collection and pilot (spec §7–9)
- `scripts/zilliz/create_collection.py`: schema exactly as spec §7 with the chosen model's dimension (BM25 function only if Phase 0 confirmed support). Idempotent: refuse to recreate an existing collection without `--recreate`.
- `scripts/zilliz/embed_upsert.py`: manifest-driven, resumable, batched by whole cases, retry with backoff, spend logging, and stale-chunk deletion when a case is re-segmented (spec §8).
- `scripts/zilliz/validate.py`: all 7 gates of spec §9.
- Run a pilot of 1,000 cases: the same 2,000-case bake-off sample's first 1,000, so it contains the verified authorities. **Run the pilot upsert twice** and show the count is unchanged.
- Commit the code on `zilliz-ingest` and tell the user it is ready for review by Claude Code.

**STOP 4.** Report: validation gate results (pass/fail with numbers); entity count after the first and second run; cost so far; and hybrid-search results (dense + BM25, `group_by` case) for the two queries above against the pilot.

### Phase 5: Full load (only after approval)
- Run the full corpus with the same scripts and settings. Checkpoint per batch and report progress every 10%.
- Run `validate.py` on the full collection.
- Load the registry into Turso table `cases_v2` (spec §11) and build an FTS5 index on it. Do not touch `case_texts`.

**STOP 5.** Report: final entity count against the manifest, all gates, total cost, total duration, and any cases that failed, with reasons. List what the backend switch (spec §12) will need.

## Definition of done
- `judgments_v1` passes every gate in spec §9 on the full corpus.
- Re-running `embed_upsert.py` on the full corpus changes nothing (0 new entities, 0 re-embeds).
- `cases_v2` in Turso matches the registry one-to-one.
- The code is on branch `zilliz-ingest` with passing tests and a `scripts/zilliz/README.md` explaining how to run each step.
- No secrets appear in code, logs or commits.
