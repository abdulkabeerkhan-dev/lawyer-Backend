# PRODUCTION HARDENING & ARCHITECTURE AUDIT REPORT
**System**: Section AI / Lawyer Backend  
**Audit Date**: October 2026  
**Auditor**: Antigravity AI Engineering  
**Scope**: Complete codebase architectural debt, redundancy, conflict, and safety audit  
**Status**: AUDIT COMPLETE — PENDING USER APPROVAL PRIOR TO REFACTOR EXECUTION  

---

## EXECUTIVE SUMMARY

A full architectural audit of the repository was conducted following successful benchmark executions of Queries 1–3. While the core retrieval, ranking, and synthesis logic is now functioning end-to-end, the codebase exhibits significant **architectural debt** accumulated during rapid iterative development. 

The most critical issue is that **`main.py` is an 7,436-line monolith** that encompasses web routing, vector retrieval, sparse indexing, court taxonomy resolution, title sanitization, prompt construction, multi-stage LLM synthesis, judicial review gate reflection, PDF binary generation, and database administration. Additionally, over **30 utility modules in `core/`** have overlapping responsibilities with `main.py`, creating circular dependencies, duplicated heuristics, and multiple conflicting paths.

This document identifies all architectural defects, categorizes them by severity, and defines the structural refactor required to transition the system to a clean, maintainable, single-source-of-truth architecture.

---

## 1. COMPREHENSIVE ARCHITECTURAL DEFECT REGISTER

| # | Category | Problem Summary | Affected Files | Severity | Recommended Fix | Execution Order |
|---|---|---|---|---|---|---|
| **D-01** | **Monolithic Coupling** | `main.py` contains 7,436 lines mixing HTTP routing, Clerk authentication, Voyage embeddings, Pinecone search, ReportLab PDF generation, prompt templates, and LLM reflection loops. | `main.py` | **CRITICAL** | Decompose `main.py` into modular services under `legal_ai/` with `main.py` serving strictly as the FastAPI routing layer. | Phase 2 |
| **D-02** | **Duplicated Search Logic** | Dense and sparse retrieval logic is implemented across 4 separate locations with inconsistent score merging and filter application. | `main.py` (`LegalSearchPipeline`), `hybrid_search.py`, `core/search_provider.py`, `core/fallback_pipeline.py` | **HIGH** | Consolidate into `legal_ai/retrieval/` with dedicated search drivers and a unified parallel orchestrator. | Phase 1 |
| **D-03** | **Duplicated Court Taxonomy & Hierarchy** | Court hierarchy weights, abbreviations, and tier mappings exist in duplicate in `core/court_taxonomy.py` and inline in `main.py` (`get_court_hierarchy_tier`). | `core/court_taxonomy.py`, `core/court_conflict_resolver.py`, `main.py` (lines 1115–1235, 3412–3525) | **HIGH** | Make `legal_ai/ranking/court_weighting.py` the single source of truth for all court normalization and hierarchy tiers. | Phase 1 |
| **D-04** | **Duplicated Case Title & Citation Extraction** | Scraper artifact removal, title extraction, and citation regex parsing are duplicated in 4 distinct modules. | `main.py` (lines 1428–1588), `core/title_parser.py`, `core/case_title_taxonomy.py`, `core/header_citation_extractor.py` | **HIGH** | Unify into `legal_ai/verification/citation_validator.py` and `legal_ai/ranking/relevance_filter.py`. | Phase 1 |
| **D-05** | **Duplicated Prompts & Inline Prompt Bloat** | LLM synthesis instructions (8-part memorandum directives) are hardcoded as multi-line strings in `main.py` in two separate branches; query planner and review gate prompts are scattered across python files. | `main.py` (lines 5828–5850, 5917–5937, 6035, 6094), `core/legal_query_planner.py`, `core/final_review_gate.py` | **HIGH** | Extract all prompts into dedicated, versioned markdown files under `prompts/` loaded via a prompt loader. | Phase 1 |
| **D-06** | **Conflicting Quality Gate Implementations** | Candidate filtering is split across 4 different functions with slightly different thresholds for dropping records. | `core/candidate_quality_filter.py`, `main.py` (`is_usable_precedent`, `passes_minimum_quality_threshold`, `classify_retrieval_trust_category`), `core/quarantine_manager.py` | **HIGH** | Consolidate into `legal_ai/ranking/relevance_filter.py` with unified hard-reject criteria. | Phase 1 |
| **D-07** | **Triple Statutory Currency Implementations** | Statutory in-force verification, amendment detection, and currency tracking are duplicated across 3 separate modules. | `core/statute_currency.py`, `core/current_law_verifier.py`, `core/statutory_validator.py` | **MEDIUM** | Unify into `legal_ai/verification/law_currency.py`. | Phase 2 |
| **D-08** | **PDF Service Fragmentation** | PDF streaming endpoint lives in `main.py`, storage downloading in `core/pdf_resolver.py`, ReportLab synthesis in `main.py`, and docket lookups in `main.py`. | `main.py` (lines 6586–6865), `core/pdf_resolver.py`, `core/document_builder.py` | **MEDIUM** | Consolidate entire resolution, storage retrieval, and ReportLab generation into `legal_ai/documents/pdf_service.py`. | Phase 1 |
| **D-09** | **Circular Dependencies** | Submodules in `core/` (`final_review_gate.py`) dynamically import from `main.py` (`from main import safe_create_anthropic_message, CLAUDE_MODEL`). | `core/final_review_gate.py`, `core/precedent_tracker.py`, `main.py` | **HIGH** | Extract client wrappers (`safe_create_anthropic_message`, model constants) into shared core utilities or configuration. | Phase 1 |
| **D-10** | **Telemetry Logging Gaps** | Retrieval telemetry prints formatted strings to stdout, but lacks source distribution percentages (`FINAL SOURCES: Supabase %, Pinecone %, BM25 %, External %`), and metrics tracking is split between console prints and `legal_ai_metrics.py`. | `main.py` (lines 5340–5370), `analytics/legal_ai_metrics.py`, `core/retrieval_logger.py` | **MEDIUM** | Unify all telemetry and pipeline metrics into `legal_ai/analytics/telemetry.py`. | Phase 1 |
| **D-11** | **Dead Code & One-Off Patch Scripts** | Root directory and `scripts/` contain 20+ one-off repair scripts, obsolete canary tests, and dead diagnostic files from previous migrations. | Root (`check_taha.py`, `check_syntax.py`, `patch_*.py`, `test_garbled.py`), `scripts/apply_mission2b_*.py` | **LOW** | Archive one-off migration scripts into `scripts/migrations/archive/` and remove obsolete root test scripts. | Phase 3 |
| **D-12** | **Inconsistent Environment & Service Role Handling** | Inconsistent fallback between `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_KEY`; varying timeouts and client instantiation across modules. | `main.py`, `core/pdf_resolver.py`, `scripts/legal_corpus_health_check.py` | **MEDIUM** | Centralize database and API clients in `legal_ai/config.py` with validated environment variables. | Phase 1 |

---

## 2. IN-DEPTH AUDIT BY SUBSYSTEM

### 2.1 Retrieval Pipeline Audit
- **Parallel Execution Status**: 
  - `LegalSearchPipeline` in `main.py` calls `search_with_components()` on `HybridSearchEngine`.
  - Proactive Supabase Postgres FTS was recently added in `main.py` using `fallback_supabase_fulltext`.
  - External search is conditionally triggered.
- **Architectural Defects**:
  1. Retrieval is not a clean, parallel `asyncio.gather()` pipeline. Supabase FTS is executed sequentially after Pinecone/BM25.
  2. Candidate pools are merged in `main.py` using ad-hoc dictionary logic (`all_pool_map`) spanning 100+ lines.
  3. `core/search_provider.py` and `core/fallback_pipeline.py` duplicate search logic and are largely bypassed by `process_query_job`.
- **Telemetry Defect**:
  - The telemetry log currently outputs `QUERY PLAN`, `SUPABASE RESULTS`, `PINECONE RESULTS`, `BM25 RESULTS`, `EXTERNAL RESULTS`, `FILTERED`, and `FINAL AUTHORITY POOL`.
  - It does **not** yet calculate the required breakdown:
    ```text
    FINAL SOURCES:
    Supabase: X%
    Pinecone: Y%
    BM25: Z%
    External: W%
    ```

### 2.2 Authority Ranking Logic Audit
- **Scoring Pipeline Status**:
  - `core/authority_ranking.py` contains `calculate_authority_score()` which evaluates court hierarchy, recency, issue match, provision match, citation validity, and text substance.
- **Architectural Defects**:
  1. `main.py` maintains an older sorting routine `rerank_by_judicial_hierarchy_and_recency` (lines 3464–3525) that operates on different criteria.
  2. `main.py` lines 3379–3411 maintains `boost_banking_fio_precedents` which hardcodes custom boosts directly in the route handler.
  3. Rejection logic is scattered: `candidate_quality_filter.py` rejects caption-only records, but `main.py` also checks `is_usable_precedent`, `passes_minimum_quality_threshold`, and `classify_retrieval_trust_category`.
- **Target Requirement**:
  - Hard reject all:
    - `caption_only` / `metadata_only`
    - `unrelated_tribunal`
    - `wrong_jurisdiction`
    - `unrelated_legal_subject`
  - Scoring factors:
    1. Legal issue semantic similarity
    2. Section/provision exact match
    3. Court hierarchy weight (Supreme Court = 1.0, High Court = 0.8, District = 0.4)
    4. Recency decay curve (2024–2026 prioritized)
    5. Citation validity match
    6. Verbatim full-text availability ($\ge 150$ words)

### 2.3 Output Layer & Memorandum Rendering Audit
- **Status**:
  - Debug warnings (`PROTOTYPE_BANNER`, completeness notices, review gate corroboration notices, `[NOT CHECKED]` currency tags) have been purged from `display_answer` via `purge_debug_warnings()`.
- **Architectural Defects**:
  1. `process_query_job` still contains leftover conditional logic and fallback strings that format notices.
  2. The memorandum synthesis prompt is duplicated at line 5828 and line 5917 of `main.py`.
  3. The reflection loop (completeness checks and review gate regeneration) is tightly coupled to the FastAPI endpoint handler, making unit testing impossible without mocking full HTTP request cycles.
- **Target Requirement**:
  - A single dedicated `MemorandumRenderer` class in `legal_ai/synthesis/memorandum_generator.py` responsible for formatting the final 8-part markdown memo and JSON precedent cards.
  - Zero internal/debug notices in `display_answer`, `precedent_cards`, or `export_documents`.

### 2.4 PDF Pipeline Audit
- **Status**:
  - Direct binary streaming (`Content-Type: application/pdf`) is now functional on `GET /api/judgments/{id}/pdf` and `GET /judgment-pdf/{id}`.
  - An automated audit of 100 random judgments from the database demonstrated **100.0% HTTP 200 OK**, **100.0% application/pdf**, and **0 authorization errors**.
- **Architectural Defects**:
  1. `find_judgment_by_id_or_canonical` (157 lines) is located inside `main.py` instead of the document service.
  2. `build_judgment_pdf_bytes` (60 lines) uses ReportLab inside `main.py`.
  3. Supabase Storage download (`fetch_storage_pdf_bytes`) lives in `core/pdf_resolver.py`.
- **Target Requirement**:
  - Consolidate all PDF resolution, storage downloads, ReportLab fallback, and path decoding into `legal_ai/documents/pdf_service.py`.

### 2.5 Prompt Architecture Audit
- **Status**:
  - `prompts/` directory currently contains only `pleading_generator.py`.
  - All primary prompts are embedded in Python files.
- **Identified Prompts**:
  1. `MASTER_SYSTEM_PROMPT` in `main.py`: ~150 lines of instructions.
  2. `synthesis_instruction` in `main.py`: 8-part memorandum directives (duplicated).
  3. `QUERY_PLANNER_SYSTEM_PROMPT` in `core/legal_query_planner.py`.
  4. `REVIEWER_SYSTEM_PROMPT` in `core/final_review_gate.py`.
  5. `QUOTE_VERIFIER_PROMPT` in `core/quote_verifier.py`.
  6. `PROPOSITION_VALIDATOR_PROMPT` in `core/proposition_validator.py`.
- **Target Requirement**:
  - Create markdown prompt files in `prompts/`:
    - `prompts/query_planner.md`
    - `prompts/researcher.md`
    - `prompts/memorandum_writer.md`
    - `prompts/reviewer.md`

### 2.6 Database / Corpus Integrity Audit
- **Audit Findings (50-precedent sample)**:
  - Cases verified in DB: 50 / 50 (100.0%)
  - Valid Citations: 50 / 50 (100.0%)
  - Verbatim Full Text: 33 / 50 (66.0%) — *34% are headnote-only or short orders*
  - Embeddings in Pinecone: 50 / 50 (100.0%)
  - PDF Availability: 50 / 50 (100.0%)
  - Section/Statute Tags in DB columns: 24 / 50 (48.0%) — *52% lack structured section tags in Postgres*
  - Ratio Decidendi extracted: 33 / 50 (66.0%)
- **Implication**:
  - Because 52% of judgments lack structured statute tags in database columns, the retrieval engine cannot rely purely on SQL `WHERE section = ...`. It must use unified multi-source retrieval (FTS + Dense + Sparse) and runtime section extraction from verbatim text.

---

## 3. COMPONENT CONFLICT & DUPLICATION MATRIX

| Capability | Component A | Component B | Component C | Component D | Resolution / Single Source of Truth |
|---|---|---|---|---|---|
| **Query Planning** | `main.py` (`expand_legal_query_doctrinally`) | `core/legal_query_planner.py` (`analyze_legal_query`) | `core/legal_skeleton.py` | `core/legal_guardrails.py` (`decompose_compound_legal_query`) | **`legal_ai/query_engine/legal_query_planner.py`** |
| **Search Orchestration** | `main.py` (`LegalSearchPipeline`) | `hybrid_search.py` (`HybridSearchEngine`) | `core/search_provider.py` | `core/fallback_pipeline.py` | **`legal_ai/retrieval/unified_orchestrator.py`** |
| **Postgres FTS Search** | `main.py` (`fallback_supabase_fulltext`) | `core/search_provider.py` (`fallback_supabase_fulltext`) | `core/fallback_pipeline.py` | — | **`legal_ai/retrieval/supabase_search.py`** |
| **Court Taxonomy & Tiers** | `core/court_taxonomy.py` | `main.py` (`get_court_hierarchy_tier`, `clean_court_name`) | `core/court_conflict_resolver.py` | — | **`legal_ai/ranking/court_weighting.py`** |
| **Candidate Quality Filtering** | `core/candidate_quality_filter.py` | `main.py` (`is_usable_precedent`, `passes_minimum_quality_threshold`) | `core/quarantine_manager.py` | `core/legal_guardrails.py` (`is_caption_only_record`) | **`legal_ai/ranking/relevance_filter.py`** |
| **Authority Ranking & Scoring** | `core/authority_ranking.py` (`rank_and_filter_authorities`) | `main.py` (`rerank_by_judicial_hierarchy_and_recency`) | `main.py` (`boost_banking_fio_precedents`) | — | **`legal_ai/ranking/authority_ranker.py`** |
| **Statute Currency Verification** | `core/statute_currency.py` (`check_statute_currency`) | `core/current_law_verifier.py` (`verify_current_law_for_provisions`) | `core/statutory_validator.py` | — | **`legal_ai/verification/law_currency.py`** |
| **Citation Extraction & Validation** | `core/header_citation_extractor.py` | `core/title_parser.py` | `main.py` (`extract_canonical_reporter_citation`) | `core/legal_guardrails.py` (`CITATION_REGEX`) | **`legal_ai/verification/citation_validator.py`** |
| **PDF Generation & Resolution** | `core/pdf_resolver.py` | `main.py` (`build_judgment_pdf_bytes`) | `main.py` (`find_judgment_by_id_or_canonical`) | `core/document_builder.py` | **`legal_ai/documents/pdf_service.py`** |
| **Telemetry & Quality Tracking** | `analytics/legal_ai_metrics.py` | `core/retrieval_logger.py` | `main.py` (inline `print` blocks) | — | **`legal_ai/analytics/telemetry.py`** |
