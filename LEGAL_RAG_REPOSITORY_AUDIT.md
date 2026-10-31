# LEGAL RAG REPOSITORY AUDIT: PAKISTANI LEGAL RESEARCH ASSISTANT

**Author**: Senior AI Infrastructure Engineer (Legal RAG Specialist)  
**Date**: October 30, 2026  
**Repository**: `lawyer-Backend` (`I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master`)  
**Target Environment**: Production / Staging RAG Pipeline  

---

## Executive Summary

This repository audit provides an exhaustive, code-grounded inspection of the 7-tier architecture powering the Pakistani Legal Retrieval-Augmented Generation (RAG) assistant. The system leverages **Voyage AI (`voyage-law-2`)** for 1024-dimension dense embeddings, **Pinecone** for vector search across superior court chunks, **Supabase PostgreSQL** (`full_judgments` table) for full-text and metadata storage, a local **BM25 index** (40,575 chunks), and an **External Judicial Crawler** for real-time court portal fallbacks.

The audit systematically catalogs all 18 requested pipeline components, details the exact end-to-end execution flow of a legal query, documents the storage and embedding specifications, isolates architectural weaknesses with direct code evidence, and highlights parameters that cannot be determined strictly from repository files.

---

## Section A: Existing Architecture Map

The pipeline follows a multi-tier, defense-in-depth retrieval architecture:

```
[User Request / Client Application]
                 │
                 ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 1: Normalization & Pre-Processing                │
 │ - Strip prompt envelopes ([Instructions:...])          │
 │ - Multi-turn conversational resolution                 │
 │ - Fast-path chitchat short-circuit                     │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 2: Doctrinal Query Planning                      │
 │ - LegalQueryPlan: issues, provisions, search lanes     │
 │ - Topic recognition & landmark authority detection     │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 3: Statutory Verification & Consensus            │
 │ - Gazette verbatim statute text injection              │
 │ - Consensus voting engine on statutory currency        │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 4: Parallel Multi-Engine Retrieval (Concurrent)  │
 │ ├─► Engine 1: Supabase PostgreSQL FTS & Citation Lookup│
 │ ├─► Engine 2: Pinecone Dense Vector (voyage-law-2)     │
 │ ├─► Engine 3: BM25 Sparse Index (40,575 chunks)        │
 │ └─► Engine 4: External Court Web Crawler (Fallback)    │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 5: Reciprocal Rank Fusion (RRF) & Weighting      │
 │ - Formula: sum(1.0 / (60 + rank)) per engine           │
 │ - Article 189 Supreme Court weighting multiplier (1.25)│
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 6: Quality Gate, Domain Quarantine & Reranking   │
 │ - Quality Gate: prune stubs, OCR noise, foreign courts │
 │ - Domain Quarantine Matrix: block cross-domain leaks   │
 │ - Relevance-Gated Authority Scoring (0-110 points)     │
 │ - Batch Supabase Trust Verification (verified_v2)      │
 │ - Top-K selection & capping (2–5 controlling cases)    │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Layer 7: Legal Synthesis & Output Verification         │
 │ - Claude 3.5 Sonnet closed-world memo drafting         │
 │ - Verbatim statutory claim support verification        │
 │ - Precedent holding scrubbing & signed PDF generation  │
 └────────────────────────────────────────────────────────┘
```

---

## Section B: File-by-File Component Inventory

### 1. Application Entry Point
- **Exact File Path**: [`main.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/main.py#L8302-L8350)
- **Main Function/Class**: `async def process_query_job(job_id: str, request: QueryRequest, authenticated_user_id: str)`
- **Input**: `job_id` (UUID), `request` (`QueryRequest`: query_text, category, messages, assistant, etc.), `authenticated_user_id` (UUID)
- **Output**: Writes completed job state, structured answer, citations, precedent cards, and early display streams to `jobs_store` and Supabase `query_jobs`.
- **Dependencies**: `FastAPI`, `pydantic`, `legal_ai.query_engine.query_processor`
- **Current Implementation**: Inspects `USE_LEGAL_AI_PIPELINE` environment variable (defaults to `true`). If true, delegates to modern pipeline `process_query_job_legal_ai`; on unhandled failure, falls back to legacy pipeline `_legacy_process_query_job`.
- **Potential Failure Points**: If `jobs_store` (in-memory dict) loses state during asynchronous worker restarts, clients polling `/jobs/{job_id}` receive 404 or stalled pending states.

### 2. Query Normalization and Processing
- **Exact File Path**: [`legal_ai/query_engine/query_processor.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L1220-L1370)
- **Main Function/Class**: `process_query_job_legal_ai` (pre-processing section)
- **Input**: Raw request text, multipart uploads, multi-turn messages array.
- **Output**: `effective_user_query: str`
- **Dependencies**: `re`
- **Current Implementation**: Strips regex prompt envelopes (`r'\[(?:What you know about this lawyer|Earlier in this conversation|Answer style|Context|Instructions?):[\s\S]*?\]'`). Traverses `messages` array: if follow-up cues (`"this"`, `"how to argue"`, `"court"`) are detected, prepends prior findings to anchor the conversational query. Checks `_CHITCHAT_EXACT` to short-circuit greetings.
- **Potential Failure Points**: If a lawyer asks an elliptical query (e.g. *"Can we plead this as a set-off?"*) without conversation history, the system lacks context to deduce what *"this"* refers to.

### 3. Legal Query Planner
- **Exact File Path**: [`core/legal_query_planner.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/legal_query_planner.py#L911-L998)
- **Main Function/Class**: `async def analyze_legal_query(query: str, ai_client_fn=None) -> LegalQueryPlan` and `create_deterministic_fallback_plan(query: str) -> LegalQueryPlan`
- **Input**: `query: str`
- **Output**: `LegalQueryPlan` dataclass (`factual_matrix`, `legal_domain`, `provisions`, `governing_statutes`, `legal_questions`, `search_lanes`, `premise_corrections`, `raw_query`)
- **Dependencies**: `anthropic`, `re`, `typing`
- **Current Implementation**: Invokes Claude 3.5 with strict prompt rules to extract legal questions, statutory provisions, and specialized multi-lane sub-queries. Preserves full query string in `factual_matrix` and `raw_query` without truncation.
- **Potential Failure Points**: In offline or rate-limited environments, Claude calls time out and fall back to `create_deterministic_fallback_plan`, which relies on hardcoded keyword triggers.

### 4. Embedding Generation
- **Exact File Path**: [`legal_ai/config.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/config.py#L60-L105) and [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L395-L434)
- **Main Function/Class**: `async def get_voyage_embedding(text: str) -> List[float]` and `embed_batch_with_retry(texts)`
- **Input**: `text: str` (query or document passage)
- **Output**: 1024-dimensional float vector
- **Dependencies**: `httpx`, `requests`, Voyage AI API
- **Current Implementation**: Sends HTTP POST to `https://api.voyageai.com/v1/embeddings` using model `voyage-law-2`. Uses `input_type="query"` for search queries and `input_type="document"` for corpus ingestion.
- **Potential Failure Points**: Synchronous network dependency; Voyage HTTP 429 rate limits or transient outages stall dense retrieval tasks.

### 5. Pinecone Index Configuration
- **Exact File Path**: [`legal_ai/config.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/config.py#L30-L58) and [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L31-L35)
- **Main Function/Class**: `get_pinecone_index()`
- **Configuration**:
  - Index Name: `os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")`
  - Namespace: `PINECONE_NAMESPACE = "judgments"`
  - Dimensions: 1024
  - Metric: Cosine
- **Dependencies**: `pinecone-client` (`from pinecone import Pinecone`)
- **Current Implementation**: Connects via `PINECONE_API_KEY` and optional `PINECONE_HOST`.
- **Potential Failure Points**: Pinecone hosted index contains zero domain metadata (`domain` / `legal_category`), making metadata pre-filtering impossible at index query time.

### 6. Supabase Database Schema
- **Exact File Path**: [`migrations/20261025_add_fts_index_full_judgments.sql`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/migrations/20261025_add_fts_index_full_judgments.sql)
- **Main Table**: `public.full_judgments`
- **Columns**: `id (UUID)`, `case_id (TEXT)`, `neutral_citation (TEXT)`, `case_title (TEXT)`, `court_name (TEXT)`, `decision_date (DATE)`, `full_text (TEXT)`, `fts_tokens (tsvector)`
- **Related Tables**: `citation_crosswalk (citation, full_judgment_id)`, `query_jobs (id, status, stage, result)`
- **Current Implementation**: GIN full-text index on `fts_tokens` weighted: A for title/citation, B for court name, C for full text (first 500k characters to prevent PostgreSQL 1MB tsvector limit error).
- **Potential Failure Points**: Missing indexed domain/subdomain columns; queries with broad keywords return noisy cross-domain matches.

### 7. Document Ingestion Pipeline
- **Exact File Path**: [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L456-L720)
- **Main Function/Class**: `run_pipeline(limit, is_dry_run, stratified_200, pause_at)`
- **Input**: `reindex_queue.json` containing case_ids
- **Output**: Chunked, embedded vectors upserted into Pinecone `judgments` namespace; checkpoint saved to `indexing_checkpoint.log`.
- **Dependencies**: `supabase`, `pinecone`, `tiktoken`, `voyageai`
- **Current Implementation**: Reads rows from Supabase `full_judgments` in batches of 25, cleans portal boilerplate, splits text into 512-token chunks, embeds with Voyage, and upserts in batches of 100 to Pinecone.
- **Potential Failure Points**: Lack of automated structural section extraction (facts vs holding vs pleadings) during ingestion.

### 8. PDF Extraction and Parsing
- **Exact File Path**: [`scripts/batch_clean_and_ingest_tier1.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_clean_and_ingest_tier1.py) and [`core/pdf_resolver.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/pdf_resolver.py)
- **Main Function/Class**: `extract_pdf_text_pypdf`, `resolve_signed_pdf_url`
- **Input**: Scraped PDF files from Pakistan Law Site and superior court portals.
- **Output**: Cleaned UTF-8 judgment text and signed Supabase storage URLs.
- **Dependencies**: `pypdf`, `supabase` storage API
- **Current Implementation**: Extracts raw text, normalizes character encoding, resolves signed download tokens (1-hour validity).
- **Potential Failure Points**: Legacy scanned judgments (1950–1980s) have poor OCR quality, resulting in misspelled party names and missing legal keywords.

### 9. Chunking Implementation
- **Exact File Path**: [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L352-L393)
- **Main Function/Class**: `chunk_judgment_text(text: str, citation: str, title: str, target_tokens: int = 512, overlap_tokens: int = 64)`
- **Input**: Cleaned judgment text, citation, case title.
- **Output**: `List[Tuple[str, int]]` (chunk text with injected context header, token count)
- **Tokenizer**: `tiktoken.get_encoding("cl100k_base")`
- **Header Injected**: `f"[{citation} | {title}]\n\n"`
- **Current Implementation**: Sliding window chunking with fixed 512 target tokens and 64 overlap tokens.
- **Potential Failure Points**: Blind token slicing breaks paragraphs, separates statutory citations from their judicial interpretations, and treats arguments of counsel identically to ratios of the bench.

### 10. Metadata Generation
- **Exact File Path**: [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L655-L671)
- **Main Function/Class**: `resolve_court_metadata`, `clean_or_extract_title`, `classify_content_type`
- **Generated Payload**:
  ```python
  {
      "case_id": cid,
      "canonical_id": cid,
      "supabase_id": supabase_id,
      "citation": raw_cit,
      "title": case_title,
      "court": court,
      "court_name": court,
      "court_normalized": court,
      "date": str(item.get("decision_date") or "")[:4],
      "year": str(item.get("decision_date") or "")[:4],
      "chunk_index": chunk_idx,
      "total_chunks": num_chunks,
      "content_type": c_type,
      "token_count": chk_tok_count,
  }
```
- **Potential Failure Points**: Metadata lacks `legal_domain` (civil, criminal, etc.), `statutes_cited`, `disposition` (allowed/dismissed), and `ratio_summary`.

### 11. Dense Retrieval
- **Exact File Path**: [`legal_ai/retrieval/pinecone_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/pinecone_search.py#L15-L93)
- **Main Function/Class**: `async def search_pinecone_dense(query_text: str, top_k: int = 40, min_similarity: float = 0.40)`
- **Input**: Query string, `top_k`, `min_similarity`
- **Output**: `List[Dict[str, Any]]` tagged with `source_type="Pinecone"`
- **Dependencies**: `Pinecone`, `voyage-law-2`
- **Current Implementation**: Computes Voyage embedding of the query, executes `index.query(namespace="judgments", vector=query_vector, top_k=top_k, include_metadata=True)`. Drops results below `min_similarity` (0.30 or 0.40).
- **Potential Failure Points**: No metadata filter can be passed to Pinecone because domain tags were not indexed; queries with multi-domain concepts experience semantic drift into criminal/banking nearest neighbors.

### 12. BM25 & PostgreSQL Full-Text Retrieval
- **Exact File Paths**:
  - BM25: [`legal_ai/retrieval/bm25_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/bm25_search.py#L14-L100)
  - Supabase FTS: [`legal_ai/retrieval/supabase_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/supabase_search.py#L75-L182)
- **Main Functions**: `search_bm25_sparse(query_text, top_k=40)` and `search_supabase_judgments(search_terms, limit_per_term=15)`
- **Input**: Search query or list of prioritized search terms (anchored provisions, landmark citations).
- **Output**: Candidate lists tagged with `source_type="BM25"` or `source_type="Supabase"`.
- **Dependencies**: Local `bm25_index.pkl` (40,575 chunks), Supabase Python client.
- **Current Implementation**:
  - BM25 performs in-memory token scoring across chunks.
  - Supabase checks exact citation match (`2021 SCMR 554`), title keyword match (`ilike`), and Postgres websearch tsquery.
- **Potential Failure Points**: BM25 latches onto common non-distinctive English words ("property", "jointly", "owned"), returning irrelevant industrial nationalization or cooperative society cases.

### 13. Reciprocal Rank Fusion Implementation
- **Exact File Path**: [`legal_ai/retrieval/unified_orchestrator.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/unified_orchestrator.py#L25-L130)
- **Main Function/Class**: `merge_candidates_with_rrf(engine_results, query_plan=None, rrf_k=60)`
- **Formula**:
  $$\text{RRF Score}(d) = \sum_{e \in \text{Engines}} \frac{1}{60 + \text{rank}_e(d)}$$
- **Input**: Dict mapping engine names (`"Supabase"`, `"Pinecone"`, `"BM25"`, `"External"`) to candidate lists.
- **Output**: Unified deduplicated candidate list sorted by fused score.
- **Constitutional Priority Multipliers**: Supreme Court of Pakistan receives $1.25\times$; binding provincial courts receive $1.15\times$; non-binding sister High Courts receive $0.65\times$ penalty when provincial target is set.
- **Potential Failure Points**: If multiple engines retrieve the same irrelevant judgment due to keyword overlap, RRF amplifies its rank over a single-engine direct precedent.

### 14. Reranking Implementation
- **Exact File Path**: [`core/authority_ranking.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/authority_ranking.py#L275-L311)
- **Main Function/Class**: `rank_and_filter_authorities(candidates, query_plan, top_k=15)` and `calculate_authority_score(candidate, query_plan)`
- **Scoring Dimensions**:
  1. Court Hierarchy (Supreme Court: 40 pts, High Court: 25 pts)
  2. Recentness (2024–2026: 30 pts, 2020–2023: 20 pts, 2010+: 12 pts)
  3. Full Text Substance (25 pts)
  4. Statutory Provision Match (25 pts)
  5. Legal Issue Match (30 pts)
  6. Citation Prestige (SCMR: 15 pts, PLD: 12 pts)
- **Relevance Gating Invariant**: If `provision_match == 0` and `issue_match == 0` and text overlap $< 2$, total score is forced to `0.0`.
- **Potential Failure Points**: No cross-encoder reranker (e.g. BGE-Reranker-Large or Jina-Reranker) is currently active in the live path; scoring relies on heuristic regex feature accumulation.

### 15. External Web Fallback
- **Exact File Path**: [`core/recent_judgments_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/recent_judgments_search.py#L74-L97) and [`legal_ai/retrieval/external_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/external_search.py)
- **Main Function/Class**: `search_recent_external_judgments(query_text, budget_s=2.5)`
- **Whitelist**: Strictly limited to official domains (`supremecourt.gov.pk`, `lahorehighcourt.gov.pk`, `sindhhighcourt.gov.pk`, `peshawarhighcourt.gov.pk`, `bhc.gov.pk`, `mis.ihc.gov.pk`).
- **Input**: Query text, time budget (2.5 seconds).
- **Output**: Candidate snippets tagged `is_external=True`, `leads_only=True`.
- **Potential Failure Points**: Unstructured portal snippets frequently lack full judicial reasoning and cannot be cited as binding precedent without human review.

### 16. Final Context Construction
- **Exact File Path**: [`legal_ai/query_engine/query_processor.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L2875-L3340)
- **Main Function/Class**: `_build_precedent_context_block(precedent_cards)` and prompt assembly.
- **Input**: Filtered precedent cards (capped at 2–5), verified statutory text block, trap instructions.
- **Output**: Grounded user prompt passed to Claude 3.5 Sonnet.
- **Enforcements**: Strict Closed-World Citation rule: LLM is forbidden from citing any superior court judgment not present in the injected cards; Negative Boundaries explicitly instruct what the case does *not* decide.
- **Potential Failure Points**: Large verbatim statutory blocks and precedent extracts can consume significant token context, risking truncated outputs if token budgets are exceeded.

### 17. LLM Answer Generation
- **Exact File Path**: [`legal_ai/query_engine/query_processor.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L4300-L4450)
- **Main Function/Class**: `safe_create_anthropic_message`
- **Model**: `claude-3-5-sonnet-20241022` (or configured `CLAUDE_MODEL`)
- **Max Output Tokens**: 8,192
- **Structure**: Mandatory 8-part Senior Counsel Memorandum or Judgment Digest format.
- **Potential Failure Points**: Model may generate plausible-sounding reasoning if context provided by retrieval is ambiguous or contradictory.

### 18. Citation and Authority Verification
- **Exact File Path**: [`core/statute_claim_verifier.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/statute_claim_verifier.py) and [`legal_ai/query_engine/query_processor.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L4815-L4950)
- **Main Function/Class**: `verify_memo_statutory_claims`, `verify_and_scrub_memo_claims`
- **Input**: Generated answer, stored statutory claims map, retrieved precedent cards.
- **Output**: Verified answer with scrubbed hallucinated citations; rejection trigger (`MemorandumVerificationBlockedError`) if unverifiable claims exceed tolerance.
- **Potential Failure Points**: Regex parser can occasionally misinterpret legitimate comparative citations (e.g. historical English or Indian cases cited within Pakistani judgments) as hallucinations.

---

## Section C: End-to-End Execution Flow (Single Query Trace)

**Example Query**: *"Find Pakistani judgments regarding partition of jointly owned property involving Benami transactions."*

1. **HTTP Post to `/query`**:
   The FastAPI route creates a job in `jobs_store` and spawns `process_query_job_legal_ai(job_id, request, user_id)`.
2. **Normalization**:
   Strips prompt headers; confirms query is not chitchat.
3. **Query Understanding (`understanding_query`)**:
   `analyze_legal_query` identifies:
   - Primary domain: `partition & property` (Civil)
   - Mandatory provisions: `Order XX Rule 18 CPC`, `Section 4 Partition Act 1893`, `Section 4 Benami Transactions (Prohibition) Act 2017`.
   - Search lanes: `partition_order20_rule18_partial_partition`, `benami_statutory_bar_section4`.
   - Premise correction: Notes that under Section 4(2) of the 2017 Act, benami defences are statutorily barred.
4. **Statutory Verification (`checking_law`)**:
   Pulls verbatim gazette text of Section 4 Partition Act and Order XX Rule 18 CPC from local verified statute store.
5. **Parallel Retrieval (`searching_precedents`)**:
   - `search_supabase_judgments` searches exact citations and provisions in PostgreSQL.
   - `search_pinecone_dense` calls Voyage API for `voyage-law-2` vector and queries Pinecone namespace `judgments`.
   - `search_bm25_sparse` searches 40,575 chunks in `bm25_index.pkl`.
   - `search_recent_external_judgments` queries superior court portals.
6. **Reciprocal Rank Fusion**:
   Fuses the four candidate streams using $RRF(k=60)$ and applies Article 189 Supreme Court weighting.
7. **Quality Gate & Domain Quarantine (`ranking_precedents`)**:
   - Drops caption-only and short stubs.
   - Cross-domain quarantine matrix executes: blocks banking recovery (FIO 2001), loan defaults, cooperative housing disputes, and criminal cases from appearing in partition queries.
   - Computes relevance-gated authority scores.
   - Retains 2 to 5 controlling authorities (e.g. *Shahbaz Khan* 2026 SCMR 941, *Khawaja Nayyar Qayyum* 2006 YLR 2059).
8. **Synthesis (`drafting_opinion`)**:
   Claude 3.5 Sonnet drafts the memorandum using only the admitted precedents and gazette statutes. Explains both the civil partition mechanism and the Section 4 statutory bar on benami defences.
9. **Verification & PDF Signing (`verifying_output`)**:
   Scavenges answer text for statute quote accuracy; signs Supabase PDF storage tokens; returns complete JSON response.

---

## Section D: Embedding Model and Configuration

- **Provider**: Voyage AI
- **Model**: `voyage-law-2`
- **Vector Dimensionality**: 1,024 dimensions
- **Input Types**:
  - `input_type="query"` for all runtime query and search lane embeddings.
  - `input_type="document"` for offline corpus chunk indexing.
- **Normalization**: L2 normalized embeddings (compatible with Pinecone cosine metric).
- **Strengths**: Tuned specifically for legal vocabulary, statutory terms, and common law reasoning.
- **Corpus Linguistic Alignment**: Excellent on Pakistani English legal prose (superior courts in Pakistan write in English). However, Urdu terms (e.g., *Tamleek*, *Hizanat*, *Mehr*, *Khula*, *Zar-i-Khula*) rely on English transliteration.

---

## Section E: Pinecone Index and Namespace Configuration

- **Index Name**: `legal-kb-pk-local` (configured via `PINECONE_INDEX_NAME`)
- **Host**: Configured via `PINECONE_HOST`
- **Namespace**: `judgments` (strictly isolated from statutory or auxiliary indexes)
- **Metric**: `cosine`
- **Indexed Payload Structure**:
  - Vector ID: `{case_id}#c{chunk_index}` (e.g. `2026_SCMR_941#c1`)
  - Vector Values: 1,024 float dimensions
  - Vector Metadata: `case_id`, `citation`, `title`, `court`, `year`, `content_type`, `token_count`.
- **Critical Limitation**: **Zero domain or statutory tags** exist in Pinecone metadata. Pinecone cannot perform metadata pre-filtering (e.g. `{"domain": {"$eq": "civil"}}`), forcing the system to rely exclusively on post-retrieval filtering.

---

## Section F: Supabase Schema and Storage Structure

- **Table**: `public.full_judgments` (estimated 431,298 total entries across Pakistan Law Site archive)
- **Columns**:
  - `id`: UUID (Primary Key)
  - `case_id`: TEXT (Unique identifier, e.g. `2006_YLR_2059`)
  - `neutral_citation`: TEXT (e.g. `2006 YLR 2059`)
  - `case_title`: TEXT (e.g. `Khawaja Nayyar Qayyum v. Zubair Qayyum`)
  - `court_name`: TEXT (Canonical court name)
  - `decision_date`: DATE
  - `full_text`: TEXT (Complete verbatim judgment text)
  - `fts_tokens`: TSVECTOR (Weighted GIN index)
- **Auxiliary Tables**:
  - `citation_crosswalk`: Resolves alternative reporter citations to canonical judgment UUIDs.
  - `query_jobs`: Asynchronous execution status and cached responses.

---

## Section G: Current Chunking and Metadata Strategy

- **Chunk Size**: Target 512 tokens (~350–400 words).
- **Overlap**: 64 tokens (~45 words).
- **Token Estimation**: `tiktoken` (`cl100k_base`).
- **Context Injection**: Each chunk begins with `[{citation} | {title}]\n\n`.
- **Deficiencies**:
  1. *Astructural*: Chunks ignore paragraph breaks, headings (e.g. *Facts*, *Submissions of Counsel*, *Judgment of the Court*), and issue divisions.
  2. *Parent-Child Disconnect*: Chunks do not reference parent document summaries or ratios decidendi.
  3. *Missing Subject Metadata*: Neither chunks nor parent records possess standardized multi-label classification tags.

---

## Section H: Current Retrieval and Ranking Strategy

The system deploys a **hybrid parallel multi-lane strategy**:
1. **Query Decomposition**: The planner extracts 2 to 5 specialized search lanes representing distinct doctrinal facets.
2. **Concurrent Fetching**:
   - Supabase FTS: targeted exact keywords and provisions.
   - Pinecone: dense semantic retrieval across all lanes.
   - BM25: local keyword retrieval across 40,575 chunks.
   - External Search: real-time superior court portal queries.
3. **Reciprocal Rank Fusion**: Merges candidates into a single priority list using $RRF(k=60)$ with constitutional court weighting (Article 189 Supreme Court priority).
4. **Candidate Quality Gate**: Hard-rejects caption-only stubs ($<100$ characters) and foreign courts.
5. **Universal Domain Quarantine**: Heuristic regex matrix prevents cross-domain noise (e.g., criminal/banking cases entering civil partition queries).
6. **Relevance-Gated Authority Scoring**: Evaluates court hierarchy, recency, full text, and statutory matches, strictly requiring non-zero relevance before granting prestige points.

---

## Section I: Existing Weaknesses Supported by Code Evidence

1. **Unfiltered Dense Retrieval in Pinecone** ([`legal_ai/retrieval/pinecone_search.py#L35`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/pinecone_search.py#L35)):
   ```python
   res = index.query(
       namespace=PINECONE_NAMESPACE,
       vector=query_vector,
       top_k=top_k,
       include_metadata=True
   )
   ```
   *Evidence*: The query call lacks a `filter` parameter. Because the index has no `domain` metadata, Pinecone retrieves any vector with high cosine similarity, regardless of legal discipline.

2. **Absence of Domain Tags in Indexing Metadata** ([`scripts/batch_vector_indexer.py#L655-L670`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L655-L670)):
   ```python
   "metadata": {
       "case_id": cid,
       "canonical_id": cid,
       "supabase_id": supabase_id,
       "citation": raw_cit,
       "title": case_title,
       "court": court,
       "year": str(item.get("decision_date") or "")[:4],
       "chunk_index": chunk_idx,
       "content_type": c_type,
       "token_count": chk_tok_count
   }
   ```
   *Evidence*: The chunk metadata records no legal domain, legal topics, or statutory identifiers.

3. **Missing Cross-Encoder Reranker** ([`legal_ai/query_engine/query_processor.py#L2374-L2432`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L2374-L2432)):
   ```python
   try:
       from legal_ai.ranking.shadow_reranker import evaluate_candidate_relevance_shadow
       shadow_candidates, shadow_rerank_stats = evaluate_candidate_relevance_shadow(...)
   except (ImportError, ModuleNotFoundError):
       shadow_candidates, shadow_rerank_stats = clean_candidates, {}
   ```
   *Evidence*: `shadow_reranker.py` does not exist on disk. Reranking relies on heuristic rule-based scoring (`core/authority_ranking.py`) rather than a trained neural cross-encoder.

4. **BM25 Lexical Keyword Collisions** ([`legal_ai/retrieval/bm25_search.py#L44`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/bm25_search.py#L44)):
   BM25 operates over bag-of-words chunks without domain context. In our live audit test, a partition query matched `2003 YLR 839` (Hydrogenated Vegetable Oil Industry Control and Development Act) simply because the text contained *"jointly owned property"*.

---

## Section J: Unknowns That Cannot Be Verified from Repository

1. **Total Number of Indexed Vectors in Production Pinecone**:
   While `bm25_index.pkl` holds exactly 40,575 chunks, the total live vector count in the production Pinecone index `legal-kb-pk-local` requires querying Pinecone's index statistics API (`index.describe_index_stats()`).
2. **Scraper Sync State on Pakistan Law Site**:
   The exact update frequency and date boundary of scraped judgments in the production Supabase database cannot be verified from the codebase alone.
3. **Hosted Cross-Encoder Infrastructure**:
   Whether a dedicated GPU sidecar or HuggingFace inference endpoint is provisioned for neural reranking is not documented in the repository configuration.
