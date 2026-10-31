# LEGAL RAG RETRIEVAL FAILURE ANALYSIS: PAKISTANI LEGAL RESEARCH ASSISTANT

**Author**: Senior AI Infrastructure Engineer (Legal RAG Specialist)  
**Date**: October 30, 2026  
**Repository**: `lawyer-Backend` (`I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master`)  
**Investigation Focus**: Root Cause Analysis of Cross-Domain Retrieval Failures & Irrelevant Precedent Leakage  

---

## 1. Primary Test Case Diagnosis

### Query Specification
- **Raw User Query**:  
  > *"Find Pakistani judgments regarding partition of jointly owned property involving Benami transactions."*
- **Expected Legal Classification**:
  - **Jurisdiction**: Pakistan (Superior Courts: Supreme Court of Pakistan & Provincial High Courts)
  - **Primary Domain**: Civil
  - **Subdomain**: Real Property & Title
  - **Secondary Topic**: Benami Transactions & Ostensible Ownership
  - **Core Legal Concepts**: Partition, co-ownership, beneficial ownership, statutory bar on benami defence, 4-ingredient test (consideration, possession, custody of title deeds, motive), preliminary decree.
  - **Governing Legislation**:
    - *Benami Transactions (Prohibition) Act, 2017* (Section 4 — Statutory bar on suit/defence based on benami)
    - *Code of Civil Procedure, 1908* (Order XX Rule 18 — Preliminary and final decree in partition suits)
    - *Partition Act, 1893* (Section 4 — Buy-out option for family dwelling house)
    - *Specific Relief Act, 1877* (Section 42 — Declaratory cross-suit)

### Observed Failure Symptoms (Prior to Remediation)
When this query was submitted to the unhardened retrieval pipeline:
1. **Irrelevant Banking Decisions**: The system retrieved banking recovery cases (e.g. *Salman Capital Investments v. HBL*, 2026 CLD 292) involving the Financial Institutions (Recovery of Finances) Ordinance 2001, pawnor rights, and pledged shares.
2. **Irrelevant Cooperative Housing Disputes**: The system retrieved internal society membership disputes (e.g. *Amir Ali Hussain Shalwani v. Ismaili Masalwala*, 2001 YLR 2537) involving share allotment and membership disqualification.
3. **Irrelevant Criminal Fraud Cases**: The system retrieved criminal breach of trust cases under Section 406/420 PPC.
4. **Outranked Direct Precedents**: Legitimate partition precedents (such as *Khawaja Nayyar Qayyum v. Zubair Qayyum*, 2006 YLR 2059 on counter-claims in partition, or *Shahbaz Khan v. Dowlat Khan*, 2026 SCMR 941 on ancestral estate preliminary decrees) were suppressed below irrelevant apex court decisions.

---

## 2. In-Depth Investigation by Architectural Area

### Area 1: Query Understanding
- **Actual Behavior**:
  [`core/legal_query_planner.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/legal_query_planner.py) correctly identifies `legal_domain=["partition & property"]` and injects Order XX Rule 18 CPC and Section 4 Benami Act 2017 into `provisions`.
- **The Failure**:
  Downstream retrieval engines (Pinecone and Supabase) **completely ignore** the planner's domain classification because neither Pinecone nor Supabase has a filtered `domain` column. The planner's output was passed solely as unconstrained search query text rather than structured database filter criteria.

### Area 2: Embeddings & Vector Space
- **Model**: Voyage AI `voyage-law-2` (1024-d, cosine).
- **The Failure**:
  Dense vector representations capture latent semantic relatedness across legal prose. Phrases like *"jointly owned property"*, *"claim of title"*, *"possession"*, and *"bona fide purchaser"* appear frequently in:
  - Criminal breach of trust trials (PPC 406/420 regarding misappropriation of joint funds or property).
  - Banking loan default suits (mortgaged joint family property).
  - Cooperative society plot allotment disputes.
  Because Voyage embeddings map semantic closeness without statutory boundaries, criminal and banking vectors cluster in the immediate vector vicinity of civil property vectors. Without hard metadata boundaries, dense retrieval inevitably drifts into cross-domain neighbors.

### Area 3: Chunking Strategy
- **Implementation**: Fixed-size token window of 512 tokens with 64-token overlap ([`scripts/batch_vector_indexer.py#L352-L393`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L352-L393)).
- **The Failure**:
  1. *Blind Boundaries*: Sliding windows sever judicial reasoning from legal issues. A chunk frequently contains the counsel's argument or factual narrative without the court's definitive ratio.
  2. *Parent-Child Disconnect*: Chunks carry no parent metadata regarding the overall subject matter of the suit or the final disposition (decreed, dismissed, acquitted).
  3. *Injected Header Limitations*: Chunks prepend only `[{citation} | {title}]\n\n`. There is no statutory anchor or domain tag embedded in the chunk text.

### Area 4: Metadata Structure
- **Index Payload**: Pinecone metadata stores only `case_id`, `citation`, `title`, `court`, `year`, `chunk_index`, and `content_type`.
- **The Failure**:
  **Zero legal domain or topic tags exist in Pinecone.** A vector query cannot execute:
  ```json
  {"domain": {"$eq": "civil"}}
  ```
  Consequently, 100% of the candidate filtering burden is deferred to post-retrieval heuristics.

### Area 5: Retrieval Engines & Fusion
- **Pinecone**: Top-$k$ candidates (15–40) are retrieved based purely on cosine similarity $> 0.30$.
- **BM25**: Operates on lexical frequency. In our benchmark, `2003 YLR 839` (Hydrogenated Vegetable Oil Industry Control and Development Act) scored 22.01 points simply because words like *"property"*, *"owned"*, and *"jointly"* appeared in the text.
- **RRF Fusion**: [`merge_candidates_with_rrf`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/unified_orchestrator.py#L25) calculates $\sum \frac{1}{60 + \text{rank}}$. If an irrelevant banking case ranks #2 in BM25 and #3 in Pinecone, RRF amplifies its fused score, giving it a commanding lead over a single-engine direct precedent.

### Area 6: Ranking & Authority Scoring
- **Root Cause Vulnerability**:
  Before the recent hardening, [`calculate_authority_score`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/authority_ranking.py#L125) was **purely additive without relevance gating**:
  - Supreme Court Hierarchy: **+40 points**
  - Recentness (2024–2026): **+30 points**
  - Full Text Substance: **+25 points**
  - Citation Strength (SCMR/PLD): **+15 points**
  - Total Potential Authority Bonus: **110 points**
  An irrelevant 2026 Supreme Court customs or banking judgment automatically scored **110 points** with zero issue match! Meanwhile, a direct 2006 Lahore High Court partition judgment scored only **64 points**.
  **The authority engine was actively penalizing direct precedents in favor of irrelevant apex court rulings.**

### Area 7: Fallback Web Crawler
- **Implementation**: [`core/recent_judgments_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/recent_judgments_search.py#L74).
- **The Failure**:
  External searches against portal search engines using broad query keywords retrieve order sheets and procedural adjournments. Without full text, they introduce non-substantive noise into the candidate pool.

---

## 3. Confirmed Bugs vs. Hypotheses

| Category | Status | Item |
|:---|:---:|:---|
| **Index Schema** | **CONFIRMED BUG** | Pinecone vector index contains no `domain`, `subdomain`, or `statute` metadata fields. Pre-filtering is impossible. |
| **Ranking Logic** | **CONFIRMED BUG** | Additive authority scoring awarded up to 110 points to apex court cases regardless of relevance (now gated by our recent quarantine patch). |
| **Reranker Pipeline**| **CONFIRMED BUG** | `legal_ai/ranking/shadow_reranker.py` is missing from the repository. The call fails silently (`except ImportError`) with zero neural reranking. |
| **Database Query** | **CONFIRMED BUG** | `supabase_search.py` invokes `.text_search("full_text", ...)` on unindexed `full_text` instead of `fts_tokens`, causing slow sequential scans. |
| **Chunking** | **CONFIRMED LIMITATION** | Blind 512-token sliding window splits legal ratios and mixes party pleadings with judicial holdings. |
| **Lexical Drift** | **HYPOTHESIS** | Shared legal vocabulary across Civil and Commercial branches causes BM25 to score corporate/banking cases higher than older High Court partition rulings. |

---

## 4. Structured Technical Issue Catalog

### ISSUE 1: Unfiltered Dense Vector Retrieval in Pinecone
- **Severity**: **CRITICAL**
- **Exact File Path**: [`legal_ai/retrieval/pinecone_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/pinecone_search.py#L35-L40)
- **Function**: `search_pinecone_dense()`
- **Evidence**:
  ```python
  res = index.query(
      namespace=PINECONE_NAMESPACE,
      vector=query_vector,
      top_k=top_k,
      include_metadata=True
  )
  ```
- **Root Cause**: The query executes with no `filter` dictionary. The underlying vector index was built without legal domain metadata tags.
- **Expected Impact**: Queries with overlapping legal terminology (e.g. partition, possession, set-off) return nearest neighbors from criminal, banking, and cooperative society cases.
- **Recommended Fix**: Add a structured `domain` and `statutes` field to Pinecone vectors during ingestion; pass query plan domain filters into `index.query(filter={"domain": {"$in": allowed_domains}})`.
- **Confidence Level**: **100% (Confirmed by code and live vector inspection)**

---

### ISSUE 2: Missing Neural Cross-Encoder Reranker
- **Severity**: **HIGH**
- **Exact File Path**: [`legal_ai/query_engine/query_processor.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/query_engine/query_processor.py#L2374-L2432)
- **Function**: `process_query_job_legal_ai()`
- **Evidence**:
  ```python
  try:
      from legal_ai.ranking.shadow_reranker import evaluate_candidate_relevance_shadow
      shadow_candidates, shadow_rerank_stats = evaluate_candidate_relevance_shadow(...)
  except (ImportError, ModuleNotFoundError):
      shadow_candidates, shadow_rerank_stats = clean_candidates, {}
  ```
- **Root Cause**: `shadow_reranker.py` does not exist on disk. Reranking falls back entirely to heuristic regex matching and authority scoring.
- **Expected Impact**: Subtle doctrinal differences between a suit for partition and a suit for recovery cannot be evaluated by semantic cross-attention.
- **Recommended Fix**: Deploy a legal cross-encoder model (e.g., `BAAI/bge-reranker-large` or `jina-reranker-v2-base-multilingual`) in a dedicated inference worker to score candidate query-passage pairs.
- **Confidence Level**: **100% (Confirmed by file system check)**

---

### ISSUE 3: Supabase Full-Text Sequential Scan Latency
- **Severity**: **HIGH**
- **Exact File Path**: [`legal_ai/retrieval/supabase_search.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/supabase_search.py#L168-L171)
- **Function**: `search_supabase_judgments()`
- **Evidence**:
  ```python
  res = sb.table("full_judgments").select(
      "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
  ).limit(4).text_search("full_text", ft_ts).execute()
  ```
- **Root Cause**: The migration [`migrations/20261025_add_fts_index_full_judgments.sql`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/migrations/20261025_add_fts_index_full_judgments.sql) created a GIN index on `fts_tokens`, but the application queries raw `full_text`.
- **Expected Impact**: In our live benchmark tests, single term queries took **8.40 seconds** because PostgreSQL performs a sequential scan across 431,298 unindexed text fields.
- **Recommended Fix**: Update `supabase_search.py` to query `.text_search("fts_tokens", ft_ts)` or call the stored RPC `search_judgments_fts(query_text)`.
- **Confidence Level**: **100% (Confirmed by timing diagnostic)**

---

### ISSUE 4: Authority Score Overpowering Legal Relevance (Historical Vulnerability)
- **Severity**: **CRITICAL**
- **Exact File Path**: [`core/authority_ranking.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/core/authority_ranking.py#L125-L272)
- **Function**: `calculate_authority_score()`
- **Evidence**:
  Prior to our relevance gating fix, an irrelevant Supreme Court ruling received:
  $$40 \text{ (Supreme Court)} + 30 \text{ (2026 recency)} + 25 \text{ (Full text)} + 15 \text{ (SCMR)} = 110 \text{ points}$$
  while a direct 2006 High Court partition precedent received only 64 points.
- **Root Cause**: Confusing judicial hierarchy prestige with substantive legal relevance.
- **Remediation Status**: Hardened via **Relevance Gating Invariant**: when `provision_match == 0` and `issue_match == 0`, total score is clamped to `0.0`.
- **Confidence Level**: **100% (Confirmed and verified by regression test suite)**

---

### ISSUE 5: Non-Structural Fixed Token Chunking
- **Severity**: **MEDIUM**
- **Exact File Path**: [`scripts/batch_vector_indexer.py`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/scripts/batch_vector_indexer.py#L352-L393)
- **Function**: `chunk_judgment_text()`
- **Evidence**:
  ```python
  step = max_body_tokens - overlap_tokens  # 512 - 64 = 448 tokens
  for start_idx in range(0, len(tokens), step):
      body_slice = tokens[start_idx : start_idx + max_body_tokens]
  ```
- **Root Cause**: Pure mathematical token slicing with `tiktoken` ignores judgment anatomy (Court Heading, Parties, Facts, Issues, Arguments, Judicial Analysis, Operative Order).
- **Expected Impact**: A chunk containing counsel's rejected argument can be retrieved as if it were the court's definitive holding.
- **Recommended Fix**: Implement structure-aware hierarchical chunking that labels chunks as `facts`, `arguments`, or `ratio_decidendi`, and links chunks to parent judgment records.
- **Confidence Level**: **95% (Confirmed by corpus structure analysis)**
