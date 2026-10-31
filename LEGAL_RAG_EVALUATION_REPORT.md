# LEGAL RAG RETRIEVAL BENCHMARK & EVALUATION REPORT

**Author**: Senior AI Infrastructure Engineer (Legal RAG Specialist)  
**Date**: October 30, 2026  
**Repository**: `lawyer-Backend` (`I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master`)  
**Evaluation Scope**: 30 Structured Realistic Pakistani Legal Queries across 6 Disciplines  
**Benchmark Artifacts**:
- Test Dataset: [`legal_retrieval_test_cases.json`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_retrieval_test_cases.json)
- Raw Results Log: [`retrieval_benchmark_results.csv`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/retrieval_benchmark_results.csv)
- Metrics Summary: `benchmark_metrics_summary.json`

---

## 1. Executive Summary & Core Metrics

We executed a controlled, reproducible retrieval benchmark across the live multi-engine architecture of the Pakistani Legal Assistant. Thirty realistic natural-language queries—spanning Civil Partition, Benami Transactions, Criminal Commercial Fraud, Constitutional Writs, Family Law, and Specialized Statutory Regimes—were tested across:
1. **Local BM25 Sparse Keyword Index** (40,575 judgment chunks)
2. **Pinecone Dense Semantic Vector Store** (`voyage-law-2` 1024-d embeddings)
3. **Supabase PostgreSQL Database** (`full_judgments` table)
4. **Reciprocal Rank Fusion (RRF)** ($k=60$ with Article 189 constitutional weighting)
5. **Final Authority Ranker & Quality Gate**

### Comprehensive Retrieval Engine Comparison (N=30 Queries)

| Retrieval Engine | Recall@5 | Recall@10 | Mean Reciprocal Rank (MRR) | Domain Mismatch Rate | Latency Profile |
|:---|:---:|:---:|:---:|:---:|:---:|
| **BM25 Sparse Lexical** | 73.3% | 83.3% | 0.552 | 33.3% | **Fast** (~0.05s) |
| **Pinecone Dense (`voyage-law-2`)** | 70.0% | 76.7% | 0.528 | 30.0% | **Medium** (~2.5s emb + 0.8s query) |
| **Supabase PostgreSQL** | 3.3% | 3.3% | 0.017 | 100.0% | **Crippling Bottleneck** (3.0s–8.4s timeouts) |
| **RRF Fused Candidates** | 73.3% | 80.0% | 0.486 | 33.3% | **Fast Fusion** (~0.01s) |
| **Final Authority Reranked** | **73.3%** | **83.3%** | **0.546** | **33.3%** | **Fast Scoring** (~0.02s) |

---

## 2. Category-by-Category Performance Analysis

The final reranked retrieval pipeline demonstrated distinct performance characteristics depending on the statutory domain:

```
Category Performance Breakdown (Final Authority Reranked):
─────────────────────────────────────────────────────────────────────────────
Civil property / partition     [6 Queries]  ───► Rel@5: 83.3% | Domain Mismatch: 16.7%
Benami transactions            [5 Queries]  ───► Rel@5: 80.0% | Domain Mismatch:  0.0%
Family law / inheritance       [5 Queries]  ───► Rel@5: 80.0% | Domain Mismatch: 20.0%
Mixed-domain statutory issues  [5 Queries]  ───► Rel@5: 80.0% | Domain Mismatch: 20.0%
Constitutional law             [4 Queries]  ───► Rel@5: 50.0% | Domain Mismatch: 50.0%
Criminal fraud / forgery       [5 Queries]  ───► Rel@5: 60.0% | Domain Mismatch: 100.0%*
─────────────────────────────────────────────────────────────────────────────
*Note: Criminal commercial fraud queries (406/420 PPC) systematically retrieve civil contractual breach precedents.
```

### Detailed Category Findings

1. **Civil Property & Partition (83.3% Recall@5, 16.7% Domain Mismatch)**:
   - *Strengths*: Highly effective at surfacing landmark partition precedents (*Shahbaz Khan v. Dowlat Khan*, 2026 SCMR 941; *Khawaja Nayyar Qayyum v. Zubair Qayyum*, 2006 YLR 2059).
   - *Weaknesses*: Legacy pre-1971 Dacca High Court partition decisions (*Kafiluddin Ahmed*, 1952 PLD 419) occasionally displace modern High Court authorities in dense vector scoring.

2. **Benami Transactions (80.0% Recall@5, 0.0% Domain Mismatch)**:
   - *Strengths*: **Zero cross-domain leaks**. Our recent implementation of the Universal Domain Quarantine and Benami Section 4 search lanes completely eliminated banking and cooperative society intrusions.
   - *Weaknesses*: Post-2017 Benami cases are scarce in the indexed corpus, causing the engine to rely on pre-2017 landmark 4-ingredient tests (*Muhammad Tazammal Hossain Talukdar*, 1958 PLD 528).

3. **Criminal Commercial Fraud & Bail (60.0% Recall@5, 100% Domain Mismatch)**:
   - *Failure Diagnosis*: Every single query concerning Sections 406/420 PPC and Section 498 CrPC retrieved civil contract cases.
   - *Root Cause*: Pakistani superior court jurisprudence on Section 406/420 frequently holds that *"criminal law cannot be set into motion to recover commercial debt or enforce civil contract"*. Because the judgments themselves extensively discuss civil contracts and specific relief, dense semantic vectors map them to the civil domain.

4. **Constitutional Law (50.0% Recall@5, 50.0% Domain Mismatch)**:
   - *Failure Diagnosis*: Broad keywords like *"Article 199 writ petition"* or *"Service Tribunal Article 212"* matched thousands of diverse administrative cases across education, police, and taxation.
   - *Root Cause*: The absence of a subdomain taxonomy (e.g., distinguishing *Civil Servant Service Appeals* from *Fundamental Rights PIL*) causes extreme semantic dilution.

5. **Family Law & Inheritance (80.0% Recall@5, 20.0% Domain Mismatch)**:
   - *Strengths*: Extremely strong landmark retrieval for Khula (*Khurshid Bibi*, PLD 1967 SC 97) and minor custody (*Welfare of Minor* principles under Guardians & Wards Act).

---

## 3. Engine-by-Engine Diagnostic Breakdown

### Engine 1: BM25 Sparse Lexical Search
- **Recall@5**: 73.3%
- **Domain Error Rate**: 33.3%
- **Behavior**:
  - BM25 excels when the user includes explicit citations (`2026 SCMR 941`) or specialized legal terms (`"Order XX Rule 18"`, `"zar-i-khula"`).
  - BM25 fails catastrophically on conversational legal queries with common English words. In query `CIV-PART-001`, `2003 YLR 839` (Hydrogenated Vegetable Oil Industry Control and Development Act) scored 22.01 points simply because words like *"property"*, *"owned"*, and *"jointly"* appeared in the text.

### Engine 2: Pinecone Dense Vector Search (`voyage-law-2`)
- **Recall@5**: 70.0%
- **Domain Error Rate**: 30.0%
- **Behavior**:
  - `voyage-law-2` captures nuanced legal concepts with high fidelity (e.g. recognizing that *"buy-out valuation by co-sharer in dwelling house"* maps directly to Section 4 of the Partition Act 1893).
  - However, because **no metadata filter** exists in Pinecone, dense search retrieves nearest neighbors without domain boundaries, allowing criminal breach of trust cases to crowd out civil partition cases.

### Engine 3: Supabase PostgreSQL Search
- **Recall@5**: 3.3%
- **Domain Error Rate**: 100.0%
- **Latency**: 3.0 to 8.4 seconds per query (frequently hitting statement timeouts)
- **Behavior**:
  - Supabase works flawlessly for exact primary key lookups (`.eq("case_id", "2026_SCMR_941")` completes in 0.7s).
  - **Catastrophic Failure on Natural Language Queries**: In [`legal_ai/retrieval/supabase_search.py#L170`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/legal_ai/retrieval/supabase_search.py#L170), the application invokes `.text_search("full_text", ...)` on the unindexed `full_text` column instead of the indexed `fts_tokens` tsvector column.
  - Furthermore, `STOP_WORDS` does not include words like *"Whether"*, *"Find"*, or *"Judgments"*. Queries starting with *"Whether a co-sharer..."* generate tsqueries like `Whether & sharer`, forcing PostgreSQL into full sequential scans across 431,298 records.

---

## 4. Human Ground-Truth Labeling Guidelines for Legal Reviewers

To support ongoing validation by Pakistani advocates and legal researchers, candidates in [`retrieval_benchmark_results.csv`](file:///I:/c/Users/kabeer/Documents/lawyer-Backend-master/lawyer-Backend-master/retrieval_benchmark_results.csv) should be audited using the following 5-tier classification framework:

1. **[HR] Highly Relevant**:
   - Direct controlling precedent on the exact legal issue and statutory provision.
   - Example: *Shahbaz Khan v. Dowlat Khan* (2026 SCMR 941) for partial partition of joint ancestral property under Order XX Rule 18 CPC.
2. **[PR] Partially Relevant**:
   - Case addresses the legal topic or procedural mechanism by analogy or in a related statutory context.
   - Example: *Khawaja Nayyar Qayyum v. Zubair Qayyum* (2006 YLR 2059) establishing that independent properties held in other co-sharers' names require an independent suit or counter-claim, not a mere defence in a partition suit.
3. **[IR] Irrelevant**:
   - Case shares common legal terminology but addresses a completely distinct factual and statutory dispute.
   - Example: Citing *Salman Capital Investments v. HBL* (2026 CLD 292, pawnor shares pledge) in a civil property partition suit.
4. **[ID] Incorrect Legal Domain**:
   - Case belongs to an entirely different branch of law (e.g. criminal state prosecution `v. The State`, customs smuggling, or service tribunal) that cannot govern the queried civil right.
5. **[RC] Relevant Cross-Domain Authority**:
   - Cross-domain decision that establishes an authoritative procedural or evidentiary principle applicable across disciplines.
   - Example: A Supreme Court constitutional ruling defining the evidentiary burden of proof for fraud under Article 117 QSO cited in a civil benami property dispute.

---

## 5. Prioritized Architectural Recommendations

1. **Implement Pinecone Metadata Pre-Filtering**:
   Add `domain: "civil" | "criminal" | "corporate" | "family" | "rent"` to Pinecone vectors. Enforce query-time filtering:
   ```python
   index.query(vector=vec, filter={"domain": {"$in": plan.allowed_domains}})
   ```
2. **Fix Supabase TSVECTOR Target**:
   Update `supabase_search.py` to query `fts_tokens` instead of `full_text`, and add query conversational stop words (`"whether"`, `"which"`, `"find"`, `"cases"`) to eliminate 8-second sequential table scans.
3. **Deploy a Dedicated Neural Cross-Encoder Reranker**:
   Replace heuristic rule-based authority ranking with a legal cross-encoder (e.g., `BAAI/bge-reranker-large` or `jina-reranker-v2`) to re-score the top 30 RRF candidates before final prompt assembly.
4. **Structure-Aware Chunking**:
   Transition from blind 512-token sliding windows to hierarchical chunking that preserves judgment headings (*Facts*, *Submissions*, *Holding / Ratio*).
