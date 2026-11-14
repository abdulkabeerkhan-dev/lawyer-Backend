# Rules: Zilliz ingestion work (lawyer-Backend)

These rules apply to every step of the Zilliz ingestion task. If a rule conflicts with an instruction you think you inferred, the rule wins. If you cannot follow a rule, stop and ask.

The full specification is `docs/ZILLIZ_MIGRATION_PLAN.md`. Read it before writing code. Where these rules and the spec disagree, stop and ask.

## Data safety
1. Source CSVs are **read-only**. Never modify, move, rename or re-save anything on `I:\`.
2. Ingest **only** these files from the root of `I:\`: `SCMR_cases.csv`, `PLD_cases.csv`, `MLD_cases.csv`, `YLR_cases.csv`, `PCRLJ_cases.csv`, `CLC_cases.csv`, `PLC_cases.csv`, `CLD_cases.csv`, `PTD_cases.csv`, `GBLR_cases.csv`.
3. **Never ingest** `I:\pakistan_law_cases.csv`, or any CSV under `I:\chrome_profile`, `I:\GoPro`, `I:\Downloads` or any other folder.
4. Do **not** write to the Turso tables `case_texts`, `case_texts_fts`, `case_pdfs` or `statute_provisions`. New Turso tables (`cases_v2`, `vector_ingest_manifest`) are allowed only when the task prompt reaches that phase.
5. Do not delete or alter any existing Pinecone, Supabase or Turso data.
6. Intermediate files (registry, chunks, embeddings cache, manifest, logs) go in `I:\zilliz_work\`. Never commit them to git.

## Identity and duplication
7. Primary key is `chunk_id = f"{case_key}:{section}:{ordinal:03d}"`. **Never** use `auto_id`, UUIDs, row numbers or hashes as the primary key.
8. `case_key = f"{year}_{journal}_{court_code}_{page}"`. The court code is **mandatory** (3,711 citations are shared across courts). Parse the citation from `Citation / Title`, never from the `Journal` column.
9. Every write to Zilliz is an `upsert` by `chunk_id`. Writes are batched by whole cases; a case is never split across batches.
10. The job must be resumable: re-running any step, after a crash or not, must produce zero duplicates. Prove this with a test (run the pilot twice; the count must not change).
11. Never re-embed a chunk whose `chunk_hash` + `embed_model` is already marked done in the manifest.
12. Parallel reports (same judgment text under two citations) are embedded **once**; the other citation goes in `parallel_citations`.

## Process
13. Work in the phases of the task prompt. **Stop at every STOP point**, post the report, and wait for explicit approval ("approved, continue") before the next phase.
14. **No full-corpus run** until the 1,000-case pilot passes all validation gates in spec §9 and the user approves.
15. When something looks wrong (counts off by more than 1% from the spec's figures, unknown court strings above 0.5%, error rates above 1%, validation gate failures), stop and report. Do not "fix" data by guessing.
16. Verify every external API detail (Zilliz/pymilvus schema and functions, BM25 function support on our tier, Voyage model limits and dimensions, batch limits) against the **current official docs** before coding. Cite the doc page in a code comment. Do not rely on memory.
17. Spending caps: embedding spend ≤ **$5** before the full run is approved; full run ≤ **$60** total. Log the token count per batch and keep a running total. Stop if a cap would be exceeded.

## Code
18. All code goes in `scripts/zilliz/` with unit tests in `tests/zilliz/`. Reuse the existing cleaner and segmenter (`core/hierarchical_legal_chunker.py`, `core/structural_judgment_segmenter.py`); extend them rather than writing parallel versions.
19. Each script supports `--dry-run`, `--limit-cases N` and `--case-keys K1,K2`, and logs progress to `I:\zilliz_work\logs\`.
20. Work on git branch **`zilliz-ingest`**, never directly on `master`. Small commits with clear messages. Do not push without the user's approval.
21. Do not change production retrieval code (`main.py`, `legal_ai/retrieval/*`, `hybrid_search.py`) in this task. The backend switch is a separate task.

## Secrets
22. Read `ZILLIZ_URI`, `ZILLIZ_TOKEN`, `VOYAGE_API_KEY`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` from `d:\lawyer-Backend\.env` only. Never print, log, commit or echo them, including in error messages and reports.

## Reporting
23. Every report states what was done, exact numbers, what failed, and what you need. Reports are factual: if a check was skipped or a test failed, say so with the output.
