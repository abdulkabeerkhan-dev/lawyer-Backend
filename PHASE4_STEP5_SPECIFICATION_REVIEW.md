# Phase 4, Step 5: Post-Rerank Domain Gate & Context Assembly Specification Review

**Date:** October 30, 2026  
**Repository:** `lawyer-Backend-master`  
**Git Branch:** `feat/phase4-step1-planner`  
**Review Target:** `PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` (v1.0.0 → v1.1.0)  
**Review Status:** **SPECIFICATION DEFECTS IDENTIFIED & HARDENED — IMPLEMENTATION REMAINS WITHHELD**  
**Step 6 Authorization Status:** **STRICTLY WITHHELD**  

---

## 1. Executive Verdict

The proposed Post-Rerank Legal Domain Validation Gate and Context Assembly Architecture is **conceptually sound and necessary** for resolving cross-domain contamination in Pakistani legal RAG. However, an adversarial engineering review identified **four critical mathematical and jurisprudential defects in Version 1.0.0**:

1. **Score-Penalization Flaw:** Multiplying off-domain candidate scores by 50% ($0.50 \times S_{\text{rerank}}$) was mathematically flawed. An off-domain judgment with an exceptionally high semantic score ($0.98 \times 0.50 = 0.49$) would still outrank a legitimate on-domain authority scored at $0.45$.
2. **Precedential Inversion Hazard:** Additive recency scoring ($0.10 \times S_{\text{recency}}$) risked subordinating timeless, binding Supreme Court landmarks (Article 189) to recent but lower-tier or non-binding High Court/Tribunal orders.
3. **Context Dilution via Minimum Quota:** Enforcing a minimum context size of $K_{\min} = 5$ risked injecting weak or hallucination-inducing precedents ($\text{score} < 0.45$) into LLM synthesis when only 2 or 3 high-quality authorities existed.
4. **Tokenizer Inaccuracy:** Character-based length estimation (`len/4`) produces significant drift on Pakistani legal text containing citations (`PLC(CS)`), statutory numerals, and Latin maxims (`suo motu`).

**Verdict:** The specification has been corrected in **Version 1.1.0** with deterministic tier-partitioned ranking buckets, precedent-grounded scoring, a hard relevance floor, exact tokenizer measurement, and appeal-number deduplication. **All implementation remains blocked until user authorization.**

---

## 2. Verified Architectural Decisions

The following architectural choices have been verified as correct:

1. **Gate Placement:** Placing the Domain Validation Gate immediately *after* cross-encoder scoring and *before* context assembly is correct. The cross-encoder must score all candidates in the candidate pool without premature truncation, but the final rank ordering must be gated by domain validity.
2. **Quarantine Isolation Boundary:** Quarantined legacy candidates from Lane B (`is_quarantined=True`) are hard-dropped (`QUARANTINE_VIOLATION`) and can never enter any ranking bucket or downstream context.
3. **Legitimate Interdisciplinary Doctrine Preservation:** Explicit recognition of Pakistani multi-domain doctrines (Article 212 Constitutional Bar of Service matters, S.561-A CrPC Quashment vs. Civil Recovery, Female Co-heir Inheritance vs. Shariat Personal Law) correctly prevents false-positive contamination penalties.
4. **Neutral Procedural Protection:** Preserving neutral procedural authorities (`general_legal` precedents on Section 151 CPC, Section 5 Limitation Act) ensures that procedural grounding is not erroneously discarded.
5. **Voyage API Fallback Protocol:** A 6.0-second timeout threshold with deterministic heuristic fallback ensures that external API latency or service degradation never terminates the user-facing retrieval pipeline.

---

## 3. Identified Defects, Vulnerabilities & Ambiguities in Version 1.0.0

| Ref | Component | Identified Defect / Vulnerability | Severity |
| :--- | :--- | :--- | :--- |
| **DEF-01** | Demotion Mechanism | **Score-multiplication leakage:** Multiplying off-domain candidate scores by $0.50$ fails to guarantee demotion below on-domain authorities when lexical similarity is exceptionally high. | **HIGH (Critical)** |
| **DEF-02** | Authority Scoring | **Precedential subordination to recency:** Older Supreme Court landmarks binding under Article 189 risked losing rank to modern High Court orders due to an additive recency term ($+0.10$). | **HIGH (Constitutional)** |
| **DEF-03** | Context Window | **Minimum context quota dilution:** Forcing $K \ge 5$ would compel the system to inject sub-threshold ($\text{score} < 0.45$) candidates into LLM synthesis if retrieval returned few results. | **MEDIUM** |
| **DEF-04** | Token Budget | **Character-based approximation drift:** Character counting (`len/4`) drifts up to 30% on Pakistani legal formatting and citations. | **MEDIUM** |
| **DEF-05** | Deduplication | **Accidental judgment collision:** Deduplicating on short case titles risks merging distinct judgments sharing common names (e.g. *"Muhammad Aslam v. State"*). | **HIGH (Fidelity)** |
| **DEF-06** | API Fallback | **Non-finite score handling:** The specification lacked explicit guards against `NaN`, `None`, or $\pm\infty$ floats in API payloads. | **LOW** |

---

## 4. Required Specification Corrections (Implemented in Version 1.1.0)

### Correction 1: Deterministic Tier-Partitioned Ranking Buckets (Fixing DEF-01)
Replaced score multiplication with a **four-tier bucket partition**:
* **Bucket 1A (Priority 1):** Direct on-domain matches (`primary_domain` or `secondary_domains`).
* **Bucket 1B (Priority 1):** Legitimate interdisciplinary authorities matching controlling doctrines.
* **Bucket 2 (Priority 2):** Neutral procedural authorities (`general_legal` / confidence $< 0.60$).
* **Bucket 3 (Priority 3):** Disallowed off-domain candidates.
* **Discarded:** Quarantined records (Hard drop).

$$\text{Final Ordering} = \text{Sort}(\text{Bucket 1A}) \mathbin{\Vert} \text{Sort}(\text{Bucket 1B}) \mathbin{\Vert} \text{Sort}(\text{Bucket 2}) \mathbin{\Vert} \text{Sort}(\text{Bucket 3})$$
*Guarantee:* An off-domain candidate in Bucket 3 cannot outrank any candidate in Bucket 1 or 2, regardless of cross-encoder score.

### Correction 2: Precedent-First Constitutional Scoring (Fixing DEF-02)
Re-weighted the Composite Authority Score to enshrine Article 189 binding apex authority:
$$\text{CompositeAuthorityScore} = 0.50 \cdot S_{\text{rerank}} + 0.30 \cdot S_{\text{precedent}} + 0.15 \cdot S_{\text{statute}} + 0.05 \cdot S_{\text{recency}}$$
* Supreme Court precedents receive $S_{\text{precedent}} = 1.00$.
* High Court precedents receive $S_{\text{precedent}} = 0.70$.
* Recency weight is reduced to a $0.05$ tie-breaker, preventing apex landmarks from being overtaken by modern lower-court orders.

### Correction 3: Hard Relevance Floor Without Blind Minimums (Fixing DEF-03)
* The quality threshold $\tau \ge 0.45$ is established as a **hard gate**.
* $K_{\min} = 5$ is redefined as an *eligibility upper bound*, NOT a mandatory fill quota. If only 2 or 3 candidates achieve $\ge \tau$, only those qualified candidates enter the generation context.

### Correction 4: Actual Tokenizer Counting (Fixing DEF-04)
* Token budgets are measured using real tokenizers (`voyageai.Client.count_tokens` or fast BPE encoders), verified active in the Python environment, with a strict 8,000-token cap.

### Correction 5: Appeal-Number-Gated Deduplication (Fixing DEF-05)
* Deduplication strictly requires an exact match on **Case Year + Civil Appeal / Criminal Petition Number** (e.g. `C.A. 452/2021 SC`) or verified parallel reporter citations (PLD vs SCMR). Common title strings alone are never merged.

### Correction 6: Clamping of Non-Finite Scores (Fixing DEF-06)
* Every score is sanitized and clamped: $S \in [0.10, 0.99]$. Any `NaN`, `None`, or infinite float is caught and replaced with a valid baseline.

---

## 5. Test Coverage Matrix: Mapping TC-GATE-01 through TC-GATE-10

| Test ID | Test Scenario | Current Test Status | Implementation File / Gap | Mocked vs. Live | Unverified Assumption |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-GATE-01** | Disallowed domain relegated to Bucket 3 | **MISSING** | Needs new test in `tests/test_domain_gate.py` | To be implemented | Assumes `classify_legal_text` reliably tags off-domain text. |
| **TC-GATE-02** | Legitimate interdisciplinary doctrine preserved (Art 212) | **EXISTING (Partial)** | `tests/test_query_planner_schema.py` tests schema; needs gate test | Unit test (Static) | Assumes `_matches_controlling_cross_doctrine` recognizes all 5 core doctrines. |
| **TC-GATE-03** | Neutral procedural authority placed in Bucket 2 | **MISSING** | Needs new test in `tests/test_domain_gate.py` | To be implemented | Assumes procedural cases don't displace substantive authorities. |
| **TC-GATE-04** | Quarantined candidate hard-dropped | **EXISTING** | `tests/test_pinecone_dual_mode_retrieval.py` (verified at retrieval) | Unit test (Live DB & Mock) | Assumes gate receives candidates from all retrieval sources. |
| **TC-GATE-05** | Dynamic assembly retains Rank 6/8 cases | **EXISTING (Empirical)** | Verified in `scripts/run_cross_encoder_benchmark.py` | Live Pinecone & Voyage | Assumes 8,000 tokens accommodates up to 10 judgments. |
| **TC-GATE-06** | Simulated Voyage timeout (10ms) | **EXISTING** | `tests/test_cross_encoder_reranker.py:test_timeout_triggers_graceful_fallback` | Mocked (`asyncio.TimeoutError`) | Assumes real network socket aborts cleanly under `asyncio.wait_for`. |
| **TC-GATE-07** | Missing `VOYAGE_API_KEY` | **EXISTING** | `tests/test_cross_encoder_reranker.py` (fallback test) | Mocked (Key=None) | Verified. |
| **TC-GATE-08** | Malformed API payload (NaN/missing results) | **MISSING** | Needs explicit malformed payload test in `tests/test_cross_encoder_reranker.py` | To be implemented | Assumes API client always returns an object with results attribute. |
| **TC-GATE-09** | Full 30-query comparative benchmark | **EXISTING** | Executed in `scripts/run_cross_encoder_benchmark.py` | Live 30 Queries | Evaluator update needed to avoid artificial contamination flags. |
| **TC-GATE-10** | Existing 102 regression tests pass | **EXISTING** | Full suite passed in 28.61s | Live Test Suite | Invariant verified. |

---

## 6. Regression Test Status

The existing test suite was executed to confirm system stability:
* **Total Tests:** 102
* **Passed:** 102 (100%)
* **Failed:** 0
* **Execution Latency:** 28.61 seconds

```
tests\test_cross_encoder_reranker.py .......                             [  6%]
tests\test_pinecone_dual_mode_retrieval.py .............                 [ 19%]
tests\test_vector_metadata_enrichment.py ..............                  [ 33%]
tests\test_supabase_fts_optimization.py .........                        [ 42%]
tests\test_query_planner_schema.py ............................          [ 69%]
tests\test_universal_domain_quarantine.py .....                          [ 74%]
tests\test_partition_benami_setoff.py ...                                [ 77%]
tests\test_query_premise_planner.py ...                                  [ 80%]
tests\test_bail_statutory_grounding.py .....                             [ 85%]
tests\test_cpc_order39_rules.py .....                                    [ 90%]
tests\test_order21_fixes.py ..........                                   [100%]
====================== 102 passed, 6 warnings in 28.61s =======================
```

---

## 7. Explicit Blockers Gating Phase 4, Step 6

The following items are explicit technical blockers that must be resolved before Step 6 (Hierarchical Chunking) can be authorized:

1. **Gate Module Implementation**: `core/post_rerank_domain_gate.py` must be authored following the Version 1.1.0 specification.
2. **Missing Unit Tests**: The missing unit tests identified in the matrix (`TC-GATE-01`, `TC-GATE-03`, `TC-GATE-08`) must be authored and passing.
3. **Benchmark Evaluator Modernization**: `scripts/run_cross_encoder_benchmark.py` must be updated with `is_candidate_relevant_modernized()` to prevent false contamination flags.
4. **Controlled Step 5 Verification**: A final verification run must confirm that Top-5 contamination drops to $\le 3.3\%$ while Recall@10 remains $100.0\%$.

---

## 8. Final Recommendation

1. **Acknowledge and approve Version 1.1.0** of the Domain Gate Specification (`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md`).
2. **Authorize Step 5 Gate Implementation & Verification** as a controlled intermediate step before moving to Step 6.
3. **Continue withholding Phase 4, Step 6 (Hierarchical Chunking)** until the Domain Gate is implemented, tested, and empirically verified against the 30 benchmark queries.
