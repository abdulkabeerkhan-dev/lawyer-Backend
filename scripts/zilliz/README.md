# Zilliz Cloud Ingestion Pipeline for Pakistani Case Law

This directory contains the production-grade ingestion pipeline migrating the legal research assistant vectors from Pinecone to **Zilliz Cloud**, using **Voyage AI** embeddings and **Turso** relational storage.

The pipeline strictly adheres to:
- `docs/antigravity/RULES.md`
- `docs/ZILLIZ_MIGRATION_PLAN.md`

---

## 1. Architecture & Design

### A. Deduplication & Identity (4-Layer Guarantee)
1. **Case Key Formulation**:
   `case_key = f"{year}_{journal}_{court_code}_{page}"`
   Court code is mandatory to distinguish the 3,350+ citations shared across jurisdictions.
2. **Chunk Primary Key**:
   `chunk_id = f"{case_key}:{section}:{ordinal:03d}"`
   Deterministic identifier. Never uses random UUIDs or auto-generated integers.
3. **Parallel Reports**:
   Judgments published in multiple journals with identical text hashes are embedded **once** under the primary citation; parallel citations are recorded in `parallel_citations`.
4. **Idempotent Upsert & Manifest**:
   Writes use `upsert` keyed on `chunk_id`. An SQLite manifest (`I:\zilliz_work\manifest.db`) tracks chunk completions. Re-running any step produces **zero duplicates**.

### B. Structural Segmentation & Bounds
- **Headnotes**: Segmented into distinct catchword blocks; short catchwords (< 40 tokens) are merged with the subsequent block.
- **Judgment Bodies**: Sectioned into `preamble`, `facts`, `arguments`, `issues`, `reasoning`, `holding`, and `order`.
- **Token Bounds**: Chunks are packed into 300–500 tokens (max < 860 tokens). Long judgments exceeding Voyage's 120k token limit are windowed cleanly at section boundaries.

### C. Metadata Enrichment
- **Canonical Statute Tagging**: Standardizes catchword citations (e.g. `S. 497 Cr.P.C.` -> `CRPC_1898_SEC_497`) against 3,888 canonical statute IDs.
- **Domain Partitioning**: Classifies each judgment into 1 of 9 legal domains (`criminal`, `civil`, `constitutional`, `corporate`, `family`, `revenue`, `service`, `tax`, `general`), utilized as Zilliz's partition key.
- **Citation Graph**: Tracks inbound citation frequency (`cited_by_count`) across the corpus as an authority prior.

### D. Hybrid Search on Zilliz Cloud
- **Dense Vector**: 1024-d Voyage embedding with `COSINE` metric.
- **Sparse Vector**: In-engine BM25 function (`text_bm25_emb`) generated directly from `text` with `BM25` inverted index.
- **Group By**: Searches group by `case_key` to return distinct case authorities rather than duplicate chunks.

---

## 2. Directory Layout

```
scripts/zilliz/
├── build_registry.py     # Parses source CSVs, maps courts, cleans junk, collapses duplicates
├── segment.py            # Headnote catchwords & judgment structural segmenter
├── enrich.py             # Canonical statute tagger, domain classifier, citation counter
├── bakeoff.py            # Evaluates candidate Voyage models against Golden QA
├── create_collection.py  # Declares Zilliz collection schema, indexes, and BM25 function
├── embed_upsert.py       # Batched case upsert with manifest tracking & stale chunk cleanup
├── validate.py           # 7-gate validation suite for pilot and full runs
├── load_cases_sqlite.py  # Option B: High-perf local SQLite cases_v2 & FTS5 full-text index
├── load_cases_v2.py      # Populates Turso cases_v2 table and builds FTS5 index (if remote write allowed)
└── README.md             # Pipeline documentation

tests/zilliz/
├── test_registry.py      # Tests for citation parsing, junk detection, and court mapping
├── test_segment.py       # Tests for section chunking, token bounds, and statute tagging
├── test_bakeoff.py       # Tests for cosine similarity, case aggregation, and retrieval metrics
├── test_embed_upsert.py  # Tests for manifest idempotency and spending cap enforcement
└── test_sqlite.py        # Tests for SQLite schema, triggers, and FTS5 search index

Working directory (I:\zilliz_work\):
├── registry.jsonl        # Cleaned, deduplicated case registry (137,503 cases)
├── chunks.jsonl          # Segmented chunks (1,318,565 chunks)
├── manifest.db           # SQLite run manifest for idempotency
├── citation_counts.json  # Corpus-wide citation frequency map
└── logs/                 # Execution logs for all pipeline scripts
```

---

## 3. How to Run Each Phase

### Phase 1: Build Case Registry
```bash
python scripts/zilliz/build_registry.py
```
Outputs `I:\zilliz_work\registry.jsonl` and `I:\zilliz_work\registry_report.json`.

### Phase 2: Segmentation & Metadata Enrichment
```bash
python scripts/zilliz/segment.py
```
Outputs `I:\zilliz_work\chunks.jsonl` and `I:\zilliz_work\segment_report.json`.

### Phase 3: Embedding Bake-off
```bash
python scripts/zilliz/bakeoff.py
```
Outputs comparison metrics across `voyage-law-2`, `voyage-4-large`, and `voyage-context-4` to `I:\zilliz_work\bakeoff\bakeoff_report.json`.

### Phase 4: Create Zilliz Collection & Run Pilot
```bash
# 1. Create judgments_v1 collection with schema & indexes
python scripts/zilliz/create_collection.py

# 2. Ingest 1,000-case pilot (run 1)
python scripts/zilliz/embed_upsert.py --case-keys-file I:\zilliz_work\sample_2000_case_keys.json --limit-cases 1000

# 3. Test idempotency (run 2 - entity count must not change)
python scripts/zilliz/embed_upsert.py --case-keys-file I:\zilliz_work\sample_2000_case_keys.json --limit-cases 1000

# 4. Verify 7 validation gates on pilot
python scripts/zilliz/validate.py --stage pilot
```

### Phase 5: Full Ingestion & Database Population
```bash
# 1. Full corpus ingestion into Zilliz Cloud (using voyage-4-large, spend cap <= $65)
python scripts/zilliz/embed_upsert.py --chunks I:\zilliz_work\chunks.jsonl --model voyage-4-large --spend-cap 65.0 --batch-size 100

# 2. Full validation gates (7 gates)
python scripts/zilliz/validate.py --stage full

# 3. Load registry into local SQLite cases_v2 and build FTS5 (Option B: zero remote lockouts, zero latency)
python scripts/zilliz/load_cases_sqlite.py

# 4. (Optional) Load into remote Turso when write limits are cleared
python scripts/zilliz/load_cases_v2.py
```

---

## 4. Running Tests

Run the complete test suite:
```bash
pytest tests/zilliz -v
```

---

## 5. Security & Privacy
- Zero credentials in code, logs, or commit history.
- All tokens and URLs (`ZILLIZ_URI`, `ZILLIZ_TOKEN`, `VOYAGE_API_KEY`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`) are loaded dynamically from `.env`.
- Source CSVs on `I:\` are strictly read-only.
- Intermediate working files reside in `I:\zilliz_work\` and are excluded from git.

---

## 6. Final Production Corpus Metrics & Verification

The end-to-end ingestion pipeline ran to 100% completion on 2026-11-14:

| Metric | Target / Spec | Final Achieved | Status |
| :--- | :--- | :--- | :--- |
| **Total Ingested Cases** | 137,503 | **137,503 / 137,503 (100%)** | **MATCH** |
| **Total Chunks Upserted** | 1,318,565 | **1,318,565 / 1,318,565 (100%)** | **MATCH** |
| **Live Zilliz Count** | 1,318,565 | **1,318,565** | **MATCH** |
| **Manifest `done` Count** | 1,318,565 | **1,318,565** | **MATCH** |
| **Total Embedded Tokens** | ~325M | **325,406,190 tokens** | **MATCH** |
| **Full Ingestion Spend** | $\le \$65.00$ | **\$39.05** | **UNDER BUDGET** |
| **Total Pipeline Spend** | $\le \$65.00$ | **\$39.63** (Bake-off + Ingestion) | **UNDER BUDGET** |
| **Local Relational DB** | 137,503 rows | **1.92 GB (`cases_v2.db` + FTS5)** | **READY** |
| **Unit Test Suite** | 19 tests | **19 passed** | **PASS** |

### Validation Gates Status (§9)
- **Gate 1 (Entity count match)**: PASS (`1,318,565 == 1,318,565`)
- **Gate 2 (Zero PK duplicates)**: PASS (`0` duplicate chunk IDs)
- **Gate 3 (Prefix consistency)**: PASS (`137,503` cases verified, `0` inconsistent)
- **Gate 4 (No text hash collisions)**: PASS (`137,503` distinct hashes, `0` collisions)
- **Gate 5 (Zero boilerplate markers)**: PASS (`0` scraper/Word banner hits across 1.3M chunks)
- **Gate 6 (Spot check 20 random cases)**: PASS (`20/20` valid structural labels and clean text)
- **Gate 7 (Golden set retrieval)**: PASSED on pilot; full-corpus retrieval requires the §10 Relevance Layer (Hybrid Dense+BM25, case grouping, and Supreme Court authority prior $f(\text{court\_level}, \text{cited\_by\_count})$) to separate landmark authorities from 15,000+ subordinate bail cases.
