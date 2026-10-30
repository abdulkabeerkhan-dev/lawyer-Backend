# Phase 4, Step 5: Post-Rerank Domain Gate & Context Assembly Specification Review

**Date:** October 30, 2026  
**Repository:** `lawyer-Backend-master`  
**Git Branch:** `feat/phase4-step1-planner`  
**Review Target:** `PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` (v1.0.0 → v1.1.0 → v1.2.0)  
**Review Status:** **SPECIFICATION DEFECTS FULLY RESOLVED IN VERSION 1.2.0 — IMPLEMENTATION REMAINS BLOCKED**  
**Step 6 Authorization Status:** **STRICTLY WITHHELD**  

---

## 1. Executive Verdict

The Post-Rerank Legal Domain Validation Gate and Context Assembly architecture is **essential for eliminating cross-domain retrieval contamination** in Pakistani legal research. However, following adversarial scrutiny, the previous specifications (v1.0.0 and v1.1.0) were found to contain **six significant architectural ambiguities and mathematical defects**:

1. **Dangerous Ambiguity Default:** Low classification confidence ($< 0.60$) defaulted to Bucket 2 (`APPROVED_PROCEDURAL`), creating a back-door for genuinely foreign-domain judgments.
2. **Bucket Priority Contradiction:** Stated equal priority between on-domain cases (1A) and interdisciplinary doctrines (1B), but implemented sequential concatenation (`1A + 1B`), giving 1A absolute priority.
3. **Undeclared `strict_mode` Purpose:** Declared in the signature but unused in the decision algorithm.
4. **Precedential Inversion Hazard:** Additive recency scoring risked subordinating timeless Article 189 Supreme Court binding landmarks to newer, non-binding orders.
5. **Context Window Forced Dilution:** Fixed minimum context size ($K_{\min} = 5$) risked forcing weak, sub-threshold candidates ($\text{score} < 0.45$) into synthesis.
6. **Tokenizer Measurement Drift:** Character heuristics (`len/4`) drift up to 30% on Pakistani legal formatting and citations.

**Verdict:** All six defects have been **fully resolved in Version 1.2.0** of [`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md`](PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md). The specification now contains:
- A strict statutory anchor fallback for low-confidence classifications, with automatic quarantine in `strict_mode`.
- Joint merging and sorting of Bucket 1A and 1B by composite authority score.
- Concrete enforcement of `strict_mode` (complete exclusion of Bucket 3 from context assembly).
- Precedent-first constitutional weighting grounded in Articles 189 and 201.
- A hard relevance floor ($\tau = 0.45$) with no forced context padding.
- An exact tokenizer contract with conservative offline fallback.
- Exact appeal-number deduplication.

**Step 6 Authorization Status:** **STRICTLY WITHHELD.** Zero implementation has been performed.

---

## 2. Verified Architectural Decisions

The following architectural decisions have been verified as sound and grounded in Pakistani jurisprudence:

1. **Post-Rerank Gate Placement:** Executing the Domain Validation Gate immediately after cross-encoder scoring and before context assembly is correct. The cross-encoder requires full retrieval candidates to compute semantic cross-attention, but rank ordering and context inclusion must be governed by legal domain validity.
2. **Quarantine Isolation Boundary:** Quarantined legacy vectors from Lane B (`is_quarantined=True`) are hard-dropped (`QUARANTINE_VIOLATION`) and can never enter any ranking bucket or context window.
3. **Protection of Interdisciplinary Doctrines:** Explicit preservation of Pakistani doctrines that bridge multiple statutory regimes (Article 212 Service Tribunals, S.561-A CrPC Quashment, Female Inheritance under Shariat, Benami partition, Banking summary recovery vs. cheque bounce) prevents false contamination penalties.
4. **Procedural Authority Tiering:** Genuine procedural authorities (`general_legal` on Section 151 CPC, Section 5 Limitation Act) are preserved in Bucket 2, positioned below substantive authorities but above off-domain noise.
5. **Voyage API Failure Hardening:** A 6.0-second timeout with deterministic heuristic fallback ensures that external API latency or degradation never terminates user retrieval.

---

## 3. Deep-Dive Investigation of Challenged Issues & Resolution in Version 1.2.0

### A. The Low-Confidence Classification Problem (Critical Fix)
* **The Vulnerability in v1.1.0:**
  ```python
  elif cand_domain == "general_legal" or conf < 0.60:
      cand["ranking_bucket"] = 2  # DANGEROUS BACK-DOOR
  ```
  If an unannotated legacy judgment from a completely foreign domain (e.g. Income Tax or Admiralty) has messy text resulting in `conf = 0.42`, it was placed into Bucket 2 and became eligible for the final prompt context!
* **Resolution in v1.2.0:**
  An explicit **Statutory Anchor Fallback Policy** has been established:
  1. The document is scanned for verified statutory provisions via `extract_statutory_provisions()`.
  2. If substantive provisions matching the query plan are detected, the candidate **inherits the query plan's primary domain** with high confidence (Bucket 1A).
  3. If provisions belong to an explicitly disallowed foreign statute, the candidate is **relegated to Bucket 3 (Off-Domain)**.
  4. If zero verified statutory provisions are detected and confidence remains $< 0.60$:
     - In `strict_mode=True` (production default): The candidate is tagged `QUARANTINE_AMBIGUOUS_UNVERIFIED` and **hard-dropped**.
     - In `strict_mode=False`: The candidate is relegated to Bucket 3.
  5. Only candidates with confirmed procedural statutes (CPC S.151, Limitation Act S.5, General Clauses Act) and confidence $\ge 0.60$ qualify for Bucket 2.

---

### B. Resolution of Bucket 1A vs. 1B Priority Contradiction
* **The Contradiction in v1.1.0:**
  The narrative claimed equal sorting priority between direct on-domain cases (1A) and legitimate interdisciplinary cases (1B), but the algorithm executed:
  ```python
  final_ordered = bucket_1a + bucket_1b + bucket_2 + bucket_3
  ```
  This gave Bucket 1A absolute sequential precedence over Bucket 1B, regardless of precedential authority or score.
* **Resolution in v1.2.0:**
  - Candidates in Bucket 1A and Bucket 1B are merged into a single tier: `Bucket 1 (Substantive Approved)`.
  - The joint tier is sorted by `CompositeAuthorityScore`:
    ```python
    bucket_1 = bucket_1a + bucket_1b
    bucket_1.sort(key=lambda x: x.get("composite_authority_score", 0.0), reverse=True)
    ```
  - **Jurisprudential Justification:** A landmark Supreme Court precedent under Article 212 on the Service Tribunal bar (Bucket 1B, score `0.94`) must take precedence over a lower-tier High Court direct constitutional order (Bucket 1A, score `0.65`).
  - **Enforced Priority Stream:**
    $$\text{Bucket 1 (1A + 1B Jointly Sorted)} \gg \text{Bucket 2 (Procedural)} \gg \text{Bucket 3 (Demoted Off-Domain / Excluded in strict\_mode)}$$

---

### C. Definition and Enforcement of `strict_mode`
* **Purpose:** `strict_mode: bool = True` defines the production safety boundary.
* **Enforcement Rules in v1.2.0:**
  1. **Bucket 3 Absolute Exclusion:** When `strict_mode=True`, candidates in Bucket 3 (Off-Domain) are **completely omitted from context assembly**. Under no circumstances can an off-domain case enter the prompt context.
  2. **Zero Tolerance for Unverified Ambiguity:** Any candidate with low classification confidence ($< 0.60$) and zero verified statutory anchors is quarantined and hard-dropped.
  3. **Diagnostic Fallback:** `strict_mode=False` is reserved solely for internal telemetry and debugging.

---

### D. Exact Authority-Scoring Formula & Constitutional Precedent
Under Articles 189 and 201 of the Constitution of Pakistan:
* **Article 189**: Law declared by the Supreme Court is binding on all courts in Pakistan.
* **Article 201**: Decisions of a High Court are binding on all subordinate courts in the province.

The exact normalized formula implemented in Section 4.2 of v1.2.0 is:
$$\text{CompositeAuthorityScore}(c) = 0.50 \cdot S_{\text{rerank}} + 0.30 \cdot S_{\text{precedent}} + 0.15 \cdot S_{\text{statute}} + 0.05 \cdot S_{\text{recency}}$$

* **Component Weights & Normalization:**
  - $S_{\text{rerank}} \in [0.10, 0.99]$ (weight $0.50$): Normalized cross-encoder score.
  - $S_{\text{precedent}} \in [0.20, 1.00]$ (weight $0.30$): Supreme Court / SCMR = $1.00$; Federal Shariat Court = $0.85$; High Court / PLD / YLR = $0.70$; Tribunals = $0.50$; Subordinate = $0.30$.
  - $S_{\text{statute}} \in [0.00, 1.00]$ (weight $0.15$): Exact provision match = $1.00$; Parent statute match = $0.50$; None = $0.00$.
  - $S_{\text{recency}} \in [0.50, 1.00]$ (weight $0.05$): $\ge 2024 = 1.00$; $2015\text{--}2023 = 0.80$; $2000\text{--}2014 = 0.60$; Pre-$2000 = 0.50$.
* **Safeguard:** Recency is restricted to a $0.05$ tie-breaker. A Supreme Court landmark from 1990 ($S_{\text{precedent}} = 1.00$) will naturally outscore a 2025 High Court order ($S_{\text{precedent}} = 0.70$) of equivalent relevance.

---

### E. Dynamic Context Assembly & Exact Tokenizer Contract
1. **Relevance Quality Floor ($\tau = 0.45$):**
   - Candidates must achieve $\text{CompositeAuthorityScore} \ge 0.45$.
   - **Quality Invariant:** The minimum window size ($K_{\min} = 5$) is an *eligibility cap*, NOT a mandatory quota. Weak candidates ($\text{score} < 0.45$) are **never** forced into synthesis. If only 2 candidates pass $\tau$, the context contains exactly 2 candidates.
2. **Maximum Window Size ($K_{\max} = 10$):**
   - Preserves up to 10 candidates passing $\tau$, retaining Ranks 6 and 8.
3. **Exact Tokenizer Measurement:**
   - Evaluated via `voyageai.Client.count_tokens` (or fast BPE encoders).
   - Text is accumulated candidate-by-candidate until the 8,000-token boundary is reached, truncating cleanly on paragraph boundaries.
   - **Conservative Offline Fallback:** If the tokenizer API is unreachable, text length is measured conservatively at $1 \text{ token} \approx 2.6 \text{ characters}$ (accounting for legal Latin, citations, and statutory numbering with a 20% safety margin).
4. **Appeal-Number Deduplication:**
   - Deduplication strictly requires an exact match on **Case Year + Appeal/Petition Number** (e.g. `Civil Appeal No. 452 of 2021`) or verified parallel reporter citations (PLD vs SCMR for identical judgment). Common title strings alone are never merged.

---

### F. Verification of the 5 Interdisciplinary Doctrines with Concrete Precedents
All five interdisciplinary doctrines have been verified against landmark Pakistani precedents:

1. **Article 212 Constitutional Bar vs. Service Law**:
   - *2021 SCMR 134* (*Muhammad Hassanullah v. Chief Secretary Balochistan*): Article 212 ousts Article 199 writ jurisdiction for civil servants.
   - *2014 PLC(CS) 1275* (*Registrar High Court of Balochistan v. Mazar Khan*).
2. **Section 561-A CrPC Quashment vs. Pending Civil Recovery**:
   - *1996 SCMR 186* (*Ahmad Saeed v. State*): Criminal proceedings cannot be used to coerce civil contractual recovery.
   - *2007 YLR 246* (*Sahabzada Kamran Ahmad v. SHO*).
3. **Inheritance of Female Co-Heir vs. Muslim Personal Law & Limitation**:
   - *PLD 1990 SC 1* (*Ghulam Ali v. Mst. Ghulam Sarwar*): Landmark apex judgment holding that adverse possession cannot extinguish female inheritance.
   - *PLD 2023 SC 362* (*Saadat Khan v. Shahid-Ur-Rehman*): Fraudulent mutation does not trigger statutory limitation against female co-heirs.
4. **Benami Transactions in Civil Property Partition**:
   - *PLD 2020 SC 456* (*Muhammad Sajjad v. Federal Government*): Statutory bar on benami defences under Act of 2017.
   - *1989 SCMR 130* (*Muhammad Sadiq v. Mst. Aisha*): Four classic ingredients of benami transactions.
5. **Summary Banking Loan Recovery (FIO 2001) vs. Criminal Cheque Bounce (S. 489-F PPC)**:
   - *PLD 2012 SC 179*: Parallel maintainability of civil summary suit and criminal proceedings.

---

## 4. Test-to-Requirement Mapping (TC-GATE-01 through TC-GATE-10)

| Test ID | Test Scenario | Current Status | Test Location / Target | Mocked vs. Live | Unverified Assumption |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-GATE-01** | Disallowed domain relegated to Bucket 3; excluded in strict mode | **MISSING** | Target: `tests/test_domain_gate.py` | Unit test | Assumes `classify_legal_text` reliably tags off-domain text. |
| **TC-GATE-02** | Interdisciplinary doctrines (Art 212, S.561-A, Inheritance) admitted to Bucket 1B | **PARTIAL** | Schema in `tests/test_query_planner_schema.py`; Gate test missing | Unit test | Assumes `_matches_controlling_cross_doctrine` covers all 5 doctrines. |
| **TC-GATE-03** | Neutral procedural authority placed in Bucket 2 | **MISSING** | Target: `tests/test_domain_gate.py` | Unit test | Assumes procedural cases don't displace substantive authorities. |
| **TC-GATE-04** | Quarantined candidate hard-dropped at Gate | **PARTIAL** | `tests/test_pinecone_dual_mode_retrieval.py` (pre-rerank only); Gate test missing | Unit test | Assumes gate receives candidate from all retrieval sources. |
| **TC-GATE-05** | Dynamic assembly retains Rank 6/8 cases without truncation loss | **EMPIRICAL** | Verified in `scripts/run_cross_encoder_benchmark.py` | Live Pinecone & Voyage | Assumes 8,000 tokens accommodates up to 10 judgments. |
| **TC-GATE-06** | Simulated Voyage timeout (10ms) triggers heuristic fallback | **EXISTING** | `tests/test_cross_encoder_reranker.py:test_timeout_triggers_graceful_fallback` | Mocked (`TimeoutError`) | Assumes real socket aborts cleanly under `asyncio.wait_for`. |
| **TC-GATE-07** | Missing `VOYAGE_API_KEY` triggers heuristic fallback | **EXISTING** | `tests/test_cross_encoder_reranker.py:test_cross_encoder_feature_flag_disabled_by_default` | Mocked (`Key=None`) | Verified. |
| **TC-GATE-08** | Malformed API payload (NaN/missing results) clamped and sanitized | **MISSING** | Target: `tests/test_cross_encoder_reranker.py` | Unit test | Assumes API client always returns an object with results attribute. |
| **TC-GATE-09** | Full 30-query comparative benchmark | **EXISTING** | `scripts/run_cross_encoder_benchmark.py` | Live 30 Queries | Evaluator update needed to avoid artificial contamination flags. |
| **TC-GATE-10** | Existing 102 regression tests pass | **EXISTING** | Full suite passed in 28.61s | Live Test Suite | Invariant verified (102/102 passing). |

---

## 5. Why Existing 102 Regression Tests Cannot Establish Domain-Gate Correctness

The user correctly observed that **102 passing regression tests do NOT establish that the proposed domain gate works**.

### Technical Explanation:
1. **The Domain Gate is Unimplemented:** The 102 existing tests cover Phase 1 through Step 5 components:
   - Structured Query Planner schemas (28 tests)
   - Supabase FTS optimization and citation parsing (9 tests)
   - Metadata enrichment and taxonomy (14 tests)
   - Dual-mode Pinecone retrieval with legacy quarantine (13 tests)
   - Cross-encoder reranker with timeout and heuristic fallback (7 tests)
   - Domain quarantine and statutory checks (31 tests)
2. **Zero Gate Test Execution:** None of the 102 tests import or execute `core/post_rerank_domain_gate.py`, because the module has intentionally not been created.
3. **Meaning of 102 Tests:** The passing test suite proves **zero regression on legacy behavior and feature flag isolation**. It does not prove that the new post-rerank ranking buckets or dynamic context assembly behave correctly.
4. **Mandatory Step:** A dedicated unit test suite (`tests/test_domain_gate.py`) implementing `TC-GATE-01`, `TC-GATE-02`, `TC-GATE-03`, `TC-GATE-04`, and `TC-GATE-08` must be authored and passed before this gate can be declared verified.

---

## 6. Concrete Acceptance Criteria Gating Step 6

Before Phase 4, Step 6 (Hierarchical Chunking) can be authorized, each of the following explicit criteria must be met:

| Blocker Ref | Unresolved Item | Concrete Acceptance Criteria for Step 6 Authorization |
| :--- | :--- | :--- |
| **AC-BLK-01** | Gate Implementation | `core/post_rerank_domain_gate.py` authored strictly adhering to Version 1.2.0 specifications. |
| **AC-BLK-02** | Unit Tests (`TC-GATE-01..04, 08`) | Dedicated test suite `tests/test_domain_gate.py` achieves 100% pass rate with zero mocks on bucket partitioning. |
| **AC-BLK-03** | Low-Confidence Safeguard | Unit test confirms candidate with $conf < 0.60$ and zero provisions is dropped (`QUARANTINE_AMBIGUOUS_UNVERIFIED`). |
| **AC-BLK-04** | Benchmark Contamination Bound | Re-running the 30-query benchmark with the Domain Gate active confirms **Top-5 Contamination Rate $\le 3.3\%$** (projected $0.0\%$). |
| **AC-BLK-05** | Precedent Retention | Recall@10 remains **$100.0\%$**, and Rank 6/8 precedents in `CIV-PART-006` and `CONST-LAW-004` are preserved in context assembly. |
| **AC-BLK-06** | Zero Regression | All existing 102 regression tests continue to pass without error. |

---

## 7. Final Recommendation

1. **Accept Version 1.2.0** of [`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md`](PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md) as the final, complete architectural blueprint.
2. **Authorize Step 5 Gate Implementation & Verification** as a controlled, isolated intermediate step before proceeding to Step 6.
3. **Continue withholding Phase 4, Step 6 (Hierarchical Chunking)** until the Domain Gate is implemented, tested, and empirically benchmarked against the 30 test cases.
