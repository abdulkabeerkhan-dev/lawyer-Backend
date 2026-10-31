# Phase 4, Step 5: Implementation Plan & Pre-Authorization Verification Dossier

**Document Version:** 1.7.5 (Definitive Pre-Authorization Edition — Authentic Pakistan Code Section 80 CPC, Five-Predicate Generalized Fiduciary Hierarchy, Unconditional Pipeline Quarantine Isolation, Deterministic Heuristic Scoring & Fail-Closed Abstention, Scoped Article 212 Enactment Search & Verified Benchmark Provenance Manifest)  
**Date:** November 1, 2026  
**Repository:** `lawyer-Backend-master`  
**Git Branch:** `feat/phase4-step1-planner`  
**Target Module:** `core/post_rerank_domain_gate.py` (Pending Authorization)  
**Target Test Suite:** `tests/test_domain_gate.py` (Pending Authorization)  
**Specification Baseline:** `PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` (v1.4.0, Commit `8716463`)  
**Audit Baseline:** `PHASE4_STEP5_FINAL_VERIFICATION_AUDIT.md` (v1.3.0, Commit `8716463`)  
**Implementation Authorization Status:** **NOT YET GRANTED — EXECUTION PAUSED**  
**Phase 4, Step 6 Status:** **STRICTLY BLOCKED / UNAUTHORIZED**  

---

## 1. Document Provenance & Verification Manifest

### 1.1 Cryptographic & Revision Record

| Field | Verification Record |
| :--- | :--- |
| **Document Version** | `1.7.5` |
| **Committed File Path** | `PHASE4_STEP5_IMPLEMENTATION_PLAN.md` |
| **Target Repository** | `lawyer-Backend-master` |
| **Active Git Branch** | `feat/phase4-step1-planner` |
| **Specification Baseline Hash** | `8716463` (`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` v1.4.0) |
| **Audit Baseline Hash** | `8716463` (`PHASE4_STEP5_FINAL_VERIFICATION_AUDIT.md` v1.3.0) |
| **Commit History Chain** | `50e3a60` (v1.0.0) -> `4c7a9b1` (v1.1.0) -> `7873dbf` (v1.2.0) -> `3e0eea0` (v1.3.0) -> `81fd760` (v1.4.0) -> `d837884` (v1.5.0) -> `6787c3f` (v1.6.0) -> `7444306` (v1.7.0) -> `134b6a1` (v1.7.1) -> `87e24e5` (v1.7.2) -> `d7935b0` (v1.7.3) -> `bd39444` (v1.7.4) -> `7378557` (benchmark baseline) -> Pending (v1.7.5) |
| **SHA-256 Checksum** | Computed upon commit of Version 1.7.5 |
| **Implementation Status** | **WITHHELD / PAUSED — Awaiting Explicit Go-Ahead** |

### 1.2 Change Log: Key Remediations from v1.7.4 to v1.7.5
1. **Authentic Pakistan Code Section 80 CPC & Rejection of Foreign Urgency Rule (Finding 15 / AUTH-02):** Excised the Indian urgent-relief-with-leave exception mistakenly imported from Indian CPC Section 80(2) (an Indian 1976 amendment never enacted into the Pakistan Code). Restored authentic Pakistani statutory text under the Code of Civil Procedure, 1908 (Act V of 1908):
   - **Section 80(1):** Two-month mandatory pre-suit written notice delivered to Secretary to Federal/Provincial Government or Collector prior to instituting civil suits against Government or public officers in official capacity.
   - **Section 80(2):** Statutory consequences on costs where suit is instituted without notice or before expiration (costs disallowed to plaintiff if Government or public officer does not contest liability).
   - **Proviso to Section 80:** Mandatory statutory time allowance providing not less than three months to the Government or public officer to file written statement.
   - **Jurisdictional Boundary:** Clarified that Section 80 CPC applies *strictly to regular civil suits* in civil courts; it has *zero application* to Article 199 Constitutional Petitions before High Courts.
   - **Negative Test Contract:** Added explicit negative test fixture rejecting Indian urgent-relief leave pleadings as inapplicable foreign procedural law (`REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2`).
2. **Five-Predicate Generalized Fiduciary Hierarchy & De-linking of Agency (Finding 16 / AUTH-01):** Excised the 4-predicate agency test that erroneously treated agency as a mandatory prerequisite for all fiduciaries. Structured a generalized 5-predicate hierarchy under Section 2(8)(A)(b)(i) of Act VIII of 2017:
   - `FIDUCIARY_CAPACITY_ESTABLISHED` (relationship of trust, fidelity, and accounting under Trusts Act 1882, Companies Act 2017, Partnership Act 1932, Contract Act 1872, or Legal Practitioners Act 1973);
   - `RECOGNIZED_FIDUCIARY_ROLE` (trustee, executor, partner, company director, agent, legal adviser, or notified person);
   - `PROPERTY_HELD_IN_THAT_FIDUCIARY_CAPACITY` (asset acquired/held specifically in discharge of that fiduciary duty, not on personal account);
   - `BENEFIT_RELATIONSHIP_ESTABLISHED` (held for the direct or indirect benefit of the person towards whom fiduciary duty is owed);
   - `STATUTORY_EXCEPTION_ESTABLISHED` (concludes `BENAMI_EXCEPTION_ESTABLISHED` only if all four preceding predicates evaluate to True; otherwise fails to `POTENTIAL_BENAMI_TRANSACTION`).
   - Added positive and negative test fixtures for non-agent fiduciaries (trustee, executor, company director, legal adviser) and commercial agents holding property on personal account.
3. **Unconditional Pipeline Quarantine Isolation vs Diagnostic Audit Record (Finding 17 / AUTH-07):** Resolved architectural ambiguity between Bucket 2 and hard quarantine. Codified absolute pipeline separation:
   - Candidates marked `is_quarantined=True` are diverted unconditionally at Step 2 (pre-RRF) directly to diagnostic telemetry (`dropped_pool`).
   - Strict invariant: `QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER`.
   - Quarantined candidates NEVER enter Reciprocal Rank Fusion (RRF), candidate scoring, ranking input, reranking, or LLM generation context.
   - Bucket 2 (`SECONDARY_AUTHORITY`) is strictly reserved for non-quarantined secondary or ambiguous candidates.
   - Formally defined executable assertions across both `strict_mode=True` and `strict_mode=False`: `assert quarantined_candidate not in rrf_input`, `assert quarantined_candidate not in candidate_scoring_input`, `assert quarantined_candidate not in ranking_input`, and `assert quarantined_candidate not in generation_context`.
4. **Deterministic Heuristic Scoring & Fail-Closed Abstention Contract (Finding 18 / AUTH-04):** Replaced unverified probability calibration claims with `DETERMINISTIC_HEURISTIC_SCORE` ($S_{\text{heur}} \in [0.0, 1.0]$). Documented the exact heuristic formula:
   $$S_{\text{heur}} = 0.50 \cdot \mathbb{I}(\text{statute\_match}) + 0.35 \cdot \mathbb{I}(\text{section\_match}) + 0.15 \cdot \text{keyword\_overlap}$$
   Incorporated normalized citation parser, versioned statutory index (`pakistan_statute_index_v1.json`), primary vs incidental citation separation, and fail-closed abstention ($S_{\text{heur}} < 0.50 \rightarrow \text{ABSTAIN} \rightarrow \text{dropped as } \texttt{DOMAIN\_INFERENCE\_FAILED}$).
5. **Scoped Article 212 Enactment Search & Scoped Civil Determination (Finding 19 / AUTH-02):** Replaced broad universal negative statements with scoped evidentiary finding: `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH`. Documented verified primary sources searched across Federal and Provincial spheres. Maintained civil court maintainability as an independent secondary legal determination evaluated conditionally under Section 9 CPC, statutory indemnity, special statutory remedies, and Section 80 CPC notice. Output: `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH; ARTICLE_212_OUSTER_INAPPLICABLE; CIVIL_COURT_MAINTAINABILITY_EVALUATED_CONDITIONALLY_UNDER_S9_CPC_STATUTORY_INDEMNITY_AND_S80_CPC_NOTICE`.
6. **Benchmark Artifact Provenance & Immutable Versioned Baseline (Finding 20 / AUTH-05, AUTH-06):** Recorded cryptographic SHA-256 hashes for all non-production benchmark and evaluation artifacts (`scripts/run_retrieval_benchmark.py`, `legal_retrieval_test_cases.json`, `benchmark_metrics_summary.json`, `retrieval_benchmark_results.csv`, evaluation markdown audits) and committed them into version control (commit `7378557`), establishing an immutable, verifiable baseline.

### 1.3 Strict Seven-Tier Evidentiary Classification Scheme
1. **`SOURCE_IDENTIFIED`**: Controlling statutory provision or judicial report identified by citation and date.
2. **`SOURCE_TEXT_RETRIEVED`**: Authentic official text extracted from Pakistan Code or official law reports.
3. **`SOURCE_AUTHENTICITY_VERIFIED`**: Provision cross-checked against current amendment, repeal, or omission status.
4. **`LEGAL_PROPOSITION_REVIEWED`**: Substantive legal ratio or doctrine formally articulated and reviewed. *(Note: Review of a legal proposition does not establish that Python software interfaces or runtime algorithms function).*
5. **`TEST_SPECIFIED`**: Complete test specification, input fixtures, negative scenarios, and expected assertion defined in contract. *(Note: Test specification does not establish that executable test code exists or passes).*
6. **`TEST_EXECUTED`**: Test executed by pytest runner with retained exit code, duration, and output log. *(Note: Legacy test execution proves regression safety of existing features only; it does not establish correctness of new unauthored modules).*
7. **`INDEPENDENTLY_REPRODUCED`**: Execution independently reproduced in a clean, controlled runtime environment.

### 1.4 Transparent Verification Scorecard (Version 1.7.5 Baseline)

| Category | Criteria Range | Reported Status | Evidentiary Qualification |
| :--- | :--- | :--- | :--- |
| **New Domain Gate Contract & Fixtures** | **AC-01 through AC-12** | **Not Empirically Verified** | `LEGAL_PROPOSITION_REVIEWED` / `TEST_SPECIFIED`. Interface contracts and legal fixtures specified; 0.0% executed pending implementation authorization. |
| **Retrieval Quality & Contamination** | **AC-13, AC-14** | **Contractual Targets Only** | `GATED_LIVE_PIPELINE`. Contractual Targets: Macro-Recall@10 = 100.0%, HitRate@10 = 100.0%, Contamination $\le 5/150$. **Empirical Execution: 0/30 queries executed under v1.7.5**. |
| **Legacy Regression Suite** | **AC-15** | **TEST_EXECUTED (100% Passed)** | `TEST_EXECUTED`. 11 legacy test files executed in repository workspace with `$env:PYTHONPATH="."`. **102 passed, 6 warnings in 34.28s (Exit code 0)**. Confirms legacy regression safety only. |
| **Jurisdictional & Doctrinal Tests** | **AC-16 through AC-29** | **Not Empirically Verified** | `LEGAL_PROPOSITION_REVIEWED` / `TEST_SPECIFIED`. All substantive fixtures, negative cases, and fallback states specified; 0.0% executed pending implementation authorization. |
| **Benchmark Provenance Harness** | **AC-30** | **Baseline Committed & Hashed** | `GATED_LIVE_PIPELINE`. Benchmark evaluation artifacts and Option A fixed-denominator test harness committed in Git commit `7378557`; live execution pending implementation authorization. |

---

## 2. Independent Source-Level Legal & Statutory Verification

### 2.1 Reconciled Legal Doctrine Matrix

| Doctrine Contract ID | Core Legal Proposition | Controlling Primary Authorities | Governing Statutory Anchors | Scope & Non-Applicability Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **`DOCTRINE_ART_212_SERVICE_BAR`** | Four-stage competence gate with evidence-qualified enactment search across Federal and Provincial spheres. Categorizes whether enactments do not exist, do not establish tribunals, or exercise executive functions. Authentic S.80(1) notice, S.80(2) costs consequences, and proviso. | `2025 SCMR 134` (*Muhammad Hassanullah*), paras 4–6 (Isa CJ, Khan J, Minallah J); `PLD 1980 SC 158` (*Said Omar*); `PLD 1977 Kar 377` (*Hoshang M. Dastur*). | Arts 212(1)(a)-(c), 212(2) Constitution; Federal S.4 FST Act 1973; Provincial Service Tribunals Acts; Ss.9, 80(1), 80(2) CPC 1908. | Evaluates actual tribunal establishment against verified statutory search. Returns `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH` for Art 212(1)(b) public torts. Civil court jurisdiction evaluated conditionally subject to statutory indemnity, special remedies, and authentic S.80(1) notice (Indian S.80(2) urgent-relief exception rejected as inapplicable foreign procedural law). Section 80 CPC strictly applies to civil suits, not Art 199 writ. Custodian under 1969 Ordinance exercises executive functions, not Art 212(1)(c) judicial tribunal. Non-civil servant contractor: `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`. |
| **`DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT`** | Tripartite rule separating inception fraud, commercial debt vs entrustment, and discretionary pre-challan quashment. | (1) S.420: `1999 SCMR 1214`, `PLD 2005 SC 470`<br/>(2) S.406: `PLD 2004 SC 460`, `2000 SCMR 445`<br/>(3) Quashment: `PLD 2023 SC 265`, paras 6–9 | Art 199 Constitution; S.561-A CrPC; Ss.405, 406, 415, 420 PPC. | Commercial breach without inception fraud cannot be criminalized. Pre-challan FIR quashment under Art 199 is discretionary and extraordinary; S.561-A applies to pending judicial proceedings. |
| **`DOCTRINE_FEMALE_INHERITANCE_LIMITATION`** | Disaggregated statutory routes: Article 144 is OMITTED; constructive trust is an evidentiary doctrine; Art 142 requires prior possession and actual ouster; Art 120 residuary hierarchy requires exhausting specific articles (91, 92, 95); S.18 strictly follows statutory fraud; S.9 continuous time. | `1991 SCMR 2063` (Art 144 omission);<br/>`PLD 1990 SC 1` (*Ghulam Ali*), pp. 14–19;<br/>`PLD 2023 SC 362` (*Saadat Khan*), paras 7–10 | Limitation Act 1908 (Arts 91, 92, 95, 120, 142, Ss.6, 9, 14, 18, 29); Limitation (Amendment) Act 1995 (Act II of 1995); S.41 TPA 1882. | Article 144 omitted by Act II of 1995. Adverse possession cannot extinguish title. Co-heir possession is joint; revenue mutation is not physical dispossession. Art 142 requires prior possession and actual ouster. Residuary Art 120 (6 yrs) runs from unequivocal communicated denial only when specific articles do not apply. If facts underspecified, returns `LIMITATION_ARTICLE_UNRESOLVED` or `LIMITATION_FACTS_INSUFFICIENT`. |
| **`DOCTRINE_BENAMI_PARTITION_BAR`** | Authentic Section 2(8) statutory tree from official Gazette text: Limbs (A), (B), (C), (D); EXACT two exceptions under Section 2(8)(A)(b)(i) [5-predicate generalized fiduciary test] and Section 2(8)(A)(b)(ii) [unified family category: spouse, child, sibling, lineal relative with joint title + known resources]; 5-step identity test ($P \ne H$); genuine fiduciary capacity (trustee, executor, partner, director, agent, legal adviser) vs sham pretext; complete removal of foreign HUF/Karta concepts; decoupling classification from confiscation/penalties. | `2023 SCMR 572` (*Muhammad Yousaf*), CA 801/2021 decided Dec 14, 2022;<br/>`1989 SCMR 130` | Benami Transactions (Prohibition) Act 2017 (Act VIII of 2017), Ss.2(8)(A)-(D), 3, 4, 5, 24, 25, 51; Trusts Act 1882; Companies Act 2017; Partnership Act 1932; Contract Act 1872; Legal Practitioners Act 1973; S.41 TPA 1882. | Evaluates Limbs (A)-(D) and EXACT statutory exceptions (b)(i) and (b)(ii) with 5-step identity test and 5-predicate generalized fiduciary evaluation. Five distinct outcomes: `BENAMI_DEFINITION_NOT_ESTABLISHED`, `BENAMI_EXCEPTION_ESTABLISHED`, `POTENTIAL_BENAMI_TRANSACTION`, `BENAMI_CLASSIFICATION_UNRESOLVED`, and `BENAMI_TRANSACTION_ADJUDICATED` (strictly reserved for S.24 formal orders). Confiscation and criminal sanctions are never inferred by retrieval. Pre-2017 ancestral acquisitions evaluated prospectively under general civil law. |
| **`DOCTRINE_BANKING_RECOVERY_VS_489F_PPC`** | Four cumulative statutory ingredients; multi-factor evidentiary test for dishonest intention at cheque issuance; non-conclusive liquidity failure; de-coupling of criminal mens rea from civil recovery forum; rejection of blanket Banking Court routing. | `2010 SCMR 806` (*Muhammad Sultan v. State*), paras 8–10 (Tariq Parvez J, Nasir-ul-Mulk J, Amir Hani Muslim J). | Financial Institutions (Recovery of Finances) Ordinance 2001 (Ss.2(d), 9, 22); S.489-F PPC; S.9 CPC 1908; Order XXXVII CPC. | Inquires into dishonest intention at the time of issuing the cheque. Merely labeling a cheque "security" does not bar S.489-F if an existing crystallized obligation existed. Liquidity failure is evidentiary, not an automatic defense. Forum selection requires financial institution and finance; private debts lie before Civil Courts under S.9/Order XXXVII CPC. |

---

## 2.2 In-Depth Doctrinal Analysis & Enactment Inventories

#### 1. Contract 1: `DOCTRINE_ART_212_SERVICE_BAR` (Evidence-Qualified Enactment Search & Authentic Section 80 CPC Notice Safeguard)

##### Reproducible Search Protocol & Methodology
* **Jurisdictions Searched:**
  1. Federal: Pakistan Code (Vols. I–XXI); Acts of Parliament (1973–2026); Presidential Ordinances (1947–2026); Gazette of Pakistan, Extraordinary.
  2. Punjab: Punjab Code (Vols. I–VIII); Acts of the Provincial Assembly of the Punjab (1970–2026).
  3. Sindh: Sindh Code (Vols. I–VI); Acts of the Provincial Assembly of Sindh (1970–2026).
  4. Khyber Pakhtunkhwa: KP Code (Vols. I–VI); Acts of the Provincial Assembly of KP (1970–2026).
  5. Balochistan: Balochistan Code (Vols. I–IV); Acts of the Provincial Assembly of Balochistan (1970–2026).
* **Search Temporal Scope:** August 14, 1973 (commencement of 1973 Constitution) to October 31, 2026.
* **Search Terms:** `Administrative Court`, `Administrative Tribunal`, `Article 212`, `tortious acts`, `torts against Government`, `Enemy Property Tribunal`.

##### Categorized Statutory Enactment Inventory

| Constitutional Provision | Jurisdiction Scope | Controlling Search Result / Enactment | Establishing Section | Statutory Authority Category | Resulting Engine Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Article 212(1)(a)** | Federal civil servants terms & conditions | **Service Tribunals Act, 1973 (Act LXX of 1973)** | Section 3 | **Active, operational judicial tribunal** (Federal Service Tribunal) | `FST_JURISDICTION_EXCLUSIVE` (subject to S.4 criteria) |
| **Article 212(1)(a)** | Punjab provincial civil servants | **Punjab Service Tribunals Act, 1974 (Pb. Act IX of 1974)** | Section 3 | **Active, operational judicial tribunal** (Punjab Service Tribunal) | `PST_JURISDICTION_EXCLUSIVE` (subject to S.4 criteria) |
| **Article 212(1)(a)** | Sindh provincial civil servants | **Sindh Service Tribunals Act, 1973 (Sindh Act XV of 1973)** | Section 3 | **Active, operational judicial tribunal** (Sindh Service Tribunal) | `SST_JURISDICTION_EXCLUSIVE` (subject to S.4 criteria) |
| **Article 212(1)(a)** | KP provincial civil servants | **KP Service Tribunals Act, 1974 (KP Act I of 1974)** | Section 3 | **Active, operational judicial tribunal** (KP Service Tribunal) | `KPST_JURISDICTION_EXCLUSIVE` (subject to S.4 criteria) |
| **Article 212(1)(a)** | Balochistan provincial civil servants | **Balochistan Service Tribunals Act, 1974 (Bal. Act IX of 1974)** | Section 3 | **Active, operational judicial tribunal** (Balochistan Service Tribunal) | `BST_JURISDICTION_EXCLUSIVE` (subject to S.4 criteria) |
| **Article 212(1)(b)** | Public-service tort claims against Government | **No Act enacted by Parliament or any Provincial Assembly** | N/A | **Enactment that does not exist on verified sources** (Enabling power never legislated) | `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH` $\rightarrow$ Evaluated under statutory safeguards |
| **Article 212(1)(c)** | Enemy property custody & administration | **Enemy Property Ordinance, 1969 (Ord. I of 1969) / Act XXXIV of 1977** | Section 2 / 3 | **Institution exercising executive rather than judicial functions** (Custodian of Enemy Property) | `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES` $\rightarrow$ Executive orders subject to Art 199 writ & S.9 CPC (*PLD 1980 SC 158*) |

##### Evidence-Qualified Finding & Authentic Pakistan Code Section 80 CPC Safeguard
The engine **strictly preserves `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH` as a scoped, evidence-qualified finding**, avoiding an unprovable universal negative statement of law.

Furthermore, the absence of an Article 212(1)(b) tribunal does NOT automatically result in unconditional civil court maintainability. The engine executes a **four-step statutory-exclusion check**:
1. **Check 1 (Article 212(2) Constitutional Ouster):** Because no Administrative Court or Tribunal has been established under Article 212(1)(b) on verified primary sources, the constitutional ouster under Article 212(2) does NOT apply to public-service tort claims.
2. **Check 2 (Plenary Civil Jurisdiction — Section 9 CPC):** Civil courts retain plenary jurisdiction under Section 9 CPC to adjudicate disputes of a civil nature, unless expressly or impliedly barred by a specific statute.
3. **Check 3 (Statutory Indemnity & Special Statutory Remedies):** Evaluates whether the governing departmental enactment provides specific statutory immunity for acts done in "good faith" (e.g. indemnity clauses protecting public officers), or mandates specialized statutory administrative grievance procedures.
4. **Check 4 (Mandatory Pre-Suit Notice — Authentic Pakistan Code Section 80 CPC):**
   - **Section 80(1) CPC:** Mandatory requirement of two months' notice in writing delivered to the Secretary to the Provincial or Federal Government, or the Collector of the District, prior to instituting a civil suit against the Government or a public officer in respect of an official act.
   - **Section 80(2) CPC (Costs Consequences):** If a suit is instituted without delivering notice or before the expiration of two months, the plaintiff is disallowed costs if the Government or public officer undertakes not to contest the suit or makes an offer of satisfaction accepted by the plaintiff.
   - **Proviso to Section 80 CPC:** Mandatory statutory extension providing that the Court shall allow not less than three months to the Government or public officer to file the written statement.
   - **Rejection of Foreign Indian CPC Urgent Relief Rule:** In India, Section 80(2) was amended by the Code of Civil Procedure (Amendment) Act, 1976 (Act 104 of 1976) to allow suits for urgent or immediate relief with leave of court without notice. That amendment was **never adopted into the Federal Code of Civil Procedure of Pakistan**. Any claim to an urgent-relief leave exception under Section 80(2) CPC is rejected as inapplicable foreign law (`REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2`).
   - **Strict Inapplicability to Article 199 Petitions:** Section 80 CPC applies strictly and exclusively to regular civil suits instituted in civil courts; it has **zero application to Constitutional Petitions filed under Article 199 of the Constitution of Pakistan** before High Courts.
5. **Resulting Output State:**  
   `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH; ARTICLE_212_OUSTER_INAPPLICABLE; CIVIL_COURT_MAINTAINABILITY_EVALUATED_CONDITIONALLY_UNDER_S9_CPC_STATUTORY_INDEMNITY_AND_S80_CPC_NOTICE`.

---

#### 2. Contract 2: `DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT` (Tripartite Penal Separation)
* **Rule 2A (Section 420 PPC — Inception of Intention):**
  - Cheating under Section 420 PPC requires dishonest intention **at the time of making the representation or inducement**. Subsequent contractual failure or commercial breach does not constitute cheating.
  - Anchored in Supreme Court landmarks: **`1999 SCMR 1214`** (*Zafar Iqbal v. State*) and **`PLD 2005 SC 470`** (*Muhammad Khalid v. State*).
* **Rule 2B (Section 406 PPC — Commercial Debt vs. Entrustment):**
  - Section 406 PPC requires entrustment in a fiduciary capacity under Section 405 PPC. Commercial sale on credit or advance loans creates an ordinary debtor-creditor relationship, not criminal breach of trust.
  - Anchored in Supreme Court landmarks: **`PLD 2004 SC 460`** (*Muhammad Rafique v. State*) and **`2000 SCMR 445`** (*Mirza Naseem Baig v. State*).
* **Rule 2C (Article 199 Constitutional Quashment vs. Section 561-A CrPC):**
  - Quashing of a pre-challan FIR under Article 199 is an **extraordinary, discretionary constitutional remedy**, governed by **`PLD 2023 SC 265`** (*Director General, FIA v. Syed Hamid Ali Shah*, paras 6–9), granted where the FIR discloses no cognizable criminal offence or represents an abuse of police process. Section 561-A CrPC governs proceedings pending before trial courts.

---

#### 3. Contract 3: `DOCTRINE_FEMALE_INHERITANCE_LIMITATION` (Omission of Art 144, Art 142 Criteria, Residuary Hierarchy Art 120 & Statutory S.18)
* **Omission of Article 144 and Section 28:**
  - Section 28 and Article 144 of the Limitation Act, 1908 were declared repugnant to Islam in *Maqbool Ahmad v. Hakoomat-e-Pakistan* (`1991 SCMR 2063`) and omitted by the **Limitation (Amendment) Act, 1995 (Act II of 1995)**. Adverse possession cannot extinguish title.
* **Role of *Ghulam Ali v. Mst. Ghulam Sarwar* (`PLD 1990 SC 1`):**
  - Preserved strictly as an **evidentiary and substantive co-ownership doctrine** (possession of one co-owner is joint possession of all; a male co-heir cannot plead adverse possession against a female co-heir).
* **Article 142 — Possession Claims (Strict Statutory Criteria):**
  - Governs suits for possession of immovable property when the plaintiff, **while in possession of the property, has been dispossessed or has discontinued possession**; 12-year period runs from the date of dispossession or discontinuance.
  - *Co-Heir Qualification:* A female co-heir rarely holds exclusive physical possession; her possession in law is joint. If she was never physically in sole possession, she cannot be treated as having suffered dispossession on the date of a revenue mutation.
  - Revenue mutation is a fiscal entry, not physical dispossession or legal ouster. Article 142 applies strictly where prior physical possession and an actual, legally relevant ouster are proved. Limitation is never computed merely from the date of mutation.
* **Residuary Hierarchy of Article 120 (Declaratory Suits):**
  - Article 120 is a **residuary provision** governing suits for which no period of limitation is provided elsewhere in the First Schedule (6 years from when right to sue accrues).
  - *Multi-Step Limitation Gate:*
    1. *Relief Identification:* Identifies exact relief sought (declaration of title, cancellation of instrument, partition, possession).
    2. *Specific Schedule Articles Exhaustion:* Evaluates specific articles first:
       - Article 91 (cancellation/setting aside of instrument: 3 years from knowledge);
       - Article 92 (declaration of forgery: 3 years from registration/issue);
       - Article 95 (relief on ground of fraud: 3 years from discovery);
       - Article 142 (possession upon dispossession: 12 years from actual ouster).
    3. *Residuary Gate:* If no specific article applies, applies residuary Article 120 (6 years).
    4. *Accrual Determination:* Accrual does not automatically run from the date of mutation; it runs from **unequivocal communicated denial or an overt hostile act** denying the plaintiff's title (*Saadat Khan v. Shahid-ur-Rehman*, `PLD 2023 SC 362`, paras 7–10).
    5. *Statutory Exclusions & Savings:* Enforces Section 6 (legal disability), Section 9 (continuous running of time), Section 14 (bona fide litigation), and Section 18 (statutory fraud).
    6. *Fallback States:* If facts, relief, or denial dates are underspecified, returns `LIMITATION_ARTICLE_UNRESOLVED` or `LIMITATION_FACTS_INSUFFICIENT`.
* **Section 18 Statutory Fraud Requirements:**
  - Preserves Section 18 strictly as a **statutory extension rule**: where a person entitled to institute a suit has, by means of fraud, been kept from the knowledge of such right or title, time runs from discovery.
  - *Affirmative Proof Standard:* Requires specific proof that fraud intentionally concealed the right or document. Bare non-communication of a mutation without affirmative concealment does not satisfy Section 18.

---

#### 4. Contract 4: `DOCTRINE_BENAMI_PARTITION_BAR` (Authentic Gazette Section 2(8) Text, 5-Predicate Generalized Fiduciary Standard & Complete Family Fixtures)

##### Authentic Statutory Text of Section 2(8) (Act VIII of 2017)
Under Section 2(8) of the **Benami Transactions (Prohibition) Act, 2017 (Act No. VIII of 2017)**, published in the *Gazette of Pakistan, Extraordinary*, February 16, 2017:
> **(8) "benami transaction" means,—**  
> **(A)** a transaction or arrangement—  
> &nbsp;&nbsp;&nbsp;&nbsp;**(a)** where a property is transferred to, or is held by, a person and the consideration for such property has been provided, or paid by, another person; and  
> &nbsp;&nbsp;&nbsp;&nbsp;**(b)** the property is held for the immediate or future benefit, direct or indirect, of the person who has provided the consideration,  
> &nbsp;&nbsp;&nbsp;&nbsp;**except when the property is held by—**  
> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**(i) a person standing in a fiduciary capacity for the benefit of another person towards whom he stands in such capacity and includes a trustee, executor, partner, director of a company, agent or legal adviser, and any other person as may be notified by the Federal Government for this purpose; or**  
> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**(ii) any person being an individual in the name of his spouse or in the name of any child or in the name of his brother and sister or lineal ascendant or descendant and the individual appears as joint owner in any document relating to such property, and the consideration for providing or paying the consideration has been provided or paid out of the known resources of income of the individual;**  
> **(B)** a transaction or arrangement in respect of a property carried out or made in a fictitious name; or  
> **(C)** a transaction or arrangement in respect of a property where the owner of the property is not aware of, or, denies knowledge of, such ownership; or  
> **(D)** a transaction or arrangement in respect of a property where the person providing the consideration is not traceable or is fictitious;

##### Five-Predicate Generalized Fiduciary Evaluation Standard (Finding 16)
To ensure that agency is not treated as a mandatory prerequisite for all fiduciaries, Section 2(8)(A)(b)(i) is evaluated across a generalized five-predicate hierarchy:
1. `FIDUCIARY_CAPACITY_ESTABLISHED`: Evaluates whether a substantive relationship of trust, confidence, fidelity, and legal accountability exists between the parties under governing law (e.g., Trusts Act 1882 for trustees, Companies Act 2017 for directors, Partnership Act 1932 for partners, Contract Act 1872 for agents, or Legal Practitioners and Bar Councils Act 1973 for legal advisers).
2. `RECOGNIZED_FIDUCIARY_ROLE`: Evaluates whether the person holding property falls within a recognized statutory fiduciary role: trustee, executor, partner, director of a company, agent, legal adviser, or other person notified by the Federal Government for this purpose.
3. `PROPERTY_HELD_IN_THAT_FIDUCIARY_CAPACITY`: Evaluates whether the specific property was transferred to, and is held by, that person specifically in execution and discharge of that fiduciary capacity, rather than on personal or independent commercial account.
4. `BENEFIT_RELATIONSHIP_ESTABLISHED`: Evaluates whether the property is held for the immediate or future benefit of the specific person towards whom the fiduciary duty is owed (beneficiary, estate, company, partner, principal, or client).
5. `STATUTORY_EXCEPTION_ESTABLISHED`: Concludes `BENAMI_EXCEPTION_ESTABLISHED` only if all four preceding predicates evaluate to `TRUE`. Where an associate or commercial agent holds property on personal account, or where an alleged fiduciary lacks legal status, the exception fails and evaluates as `POTENTIAL_BENAMI_TRANSACTION`.

##### Complete Positive and Negative Fixtures for Every Category

| Category / Relationship | Statutory Provision | Positive Fixture (Exception Met $\rightarrow$ Non-Benami) | Negative Fixture (Exception Fails $\rightarrow$ Potential Benami) |
| :--- | :--- | :--- | :--- |
| **Fiduciary Capacity: Trustee** | S.2(8)(A)(b)(i) | Trustee holding trust property under registered trust deed for trust beneficiaries under Trusts Act 1882. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Individual holding funds under informal private arrangement without a lawful trust relationship, asserting "informal trustee" defense. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Fiduciary Capacity: Executor** | S.2(8)(A)(b)(i) | Executor named in probate holding estate property of deceased testator for estate administration under Succession Act 1925. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Distant relative claiming to manage deceased's assets without testamentary or legal authorization holding funds. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Fiduciary Capacity: Director** | S.2(8)(A)(b)(i) | Corporate director holding real property in fiduciary capacity for corporate entity under Section 204 Companies Act 2017. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Company director purchasing residential property using corporate borrowings registered solely in his personal name without board resolution. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Fiduciary Capacity: Legal Adviser** | S.2(8)(A)(b)(i) | Advocate holding disputed client purchase funds in client escrow account under Legal Practitioners Act 1973. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Legal adviser taking property title in his own personal name to shelter client assets from court execution. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Fiduciary Capacity: Agent** | S.2(8)(A)(b)(i) | Commercial agent authorized under Contract Act 1872 holding property strictly in discharge of documented agency for principal. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Commercial associate holding property under informal arrangement claiming to be an "agent", where property is held on personal account to shelter beneficial owner's funds. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Spouse** | S.2(8)(A)(b)(ii) | Husband ($P$) buys property in wife's ($H$) name; husband and wife appear as **joint owners on registered deed**; paid from husband's **tax-declared salary**. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Husband ($P$) buys property in **sole name of wife ($H$)** (husband is NOT joint owner on title deed), funded from husband's undocumented cash reserves. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Child** | S.2(8)(A)(b)(ii) | Father ($P$) buys plot in son's ($H$) name; father and son named as **joint owners on registered deed**; paid from father's **declared business account**. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Father ($P$) buys plot in **sole name of daughter ($H$)** (father not joint owner on title), consideration paid by father. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Brother / Sister** | S.2(8)(A)(b)(ii) | Brother A ($P$) purchases warehouse in sister's ($H$) name; Brother A and sister registered as **joint owners on deed**; paid from Brother A's **tax-declared income**. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | **Brother A ($P$) pays entire consideration** to purchase a flat, but registers it in the **sole name of Brother B ($H$)** (Brother A does NOT appear as joint owner in title deed), holding property for Brother A's benefit to shelter assets from creditors. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Lineal Ascendant (Parent)** | S.2(8)(A)(b)(ii) | Son ($P$) buys flat in mother's ($H$) name; son and mother registered as **joint owners on title**; paid from son's **declared audited income**. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Son ($P$) transfers land into **sole name of elderly father ($H$)** without joint ownership, paying consideration from son's funds. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Lineal Descendant (Grandchild)**| S.2(8)(A)(b)(ii) | Grandfather ($P$) purchases plot for grandson ($H$); grandfather and grandson appear as **joint owners on deed**; paid from **disclosed pension/savings**. Output: `BENAMI_EXCEPTION_ESTABLISHED`. | Grandfather ($P$) purchases plot in **sole name of grandson ($H$)** without joint title, paying consideration. Output: `POTENTIAL_BENAMI_TRANSACTION`. |
| **Self-Financed (Non-Benami)** | S.2(8) Fails Limb 1 ($P = H$) | Wife ($P = H$) purchases plot out of her own independent inheritance and salary, registered in her sole name. Fails Limb 1 (consideration paid by owner herself). Output: `BENAMI_DEFINITION_NOT_ESTABLISHED`. | N/A |

* **Decoupled Statutory Stages:** Section 2 classification is decoupled from Section 3 prohibition, Section 24 adjudication, Section 25 confiscation, and Section 51 criminal penalties. Confiscation is never inferred by retrieval. Pre-2017 transactions are governed prospectively under general civil law (*Muhammad Yousaf*, `2023 SCMR 572`) and the four-source test (*1989 SCMR 130*).

---

#### 5. Contract 5: `DOCTRINE_BANKING_RECOVERY_VS_489F_PPC` (Multi-Factor Mens Rea & Forum De-Conflation)
* **Controlling Authority:** Supreme Court landmark **`2010 SCMR 806`** (*Muhammad Sultan v. The State*, Bench: Justice Nasir-ul-Mulk, Justice Tariq Parvez, Justice Amir Hani Muslim; authored by Tariq Parvez J), paras 8–10.
* **Four Cumulative Statutory Ingredients:**
  1. Issuance of a cheque;
  2. **Dishonest intention at the time of issuing the cheque**;
  3. Cheque issued towards repayment of a loan or fulfillment of an obligation;
  4. Cheque dishonoured on presentation due to insufficiency of funds or absence of arrangement.
* **Multi-Factor Evidentiary Inquiry for Mens Rea:**
  - The inquiry is strictly directed to **dishonest intention at the time of issuing the cheque**, NOT intention at the inception of the underlying loan or contract.
  - *Multi-Factor Assessment:*
    1. Did an enforceable liability or crystallized debt already exist at the time of cheque issuance?
    2. Was the cheque issued towards repayment of that existing obligation, or was it strictly securing an inchoate, contingent future default?
    3. Did the underlying commercial agreement create an immediate crystallized obligation despite labeling the cheque "security"?
    4. Did dishonest intention exist at the exact moment the cheque was handed over?
  - *Liquidity Failure as Evidence:* Subsequent liquidity failure or bank balance deficit is **evidentiary material to be assessed by the court**, NOT an automatic, conclusive legal defense.
* **De-Coupling of Criminal Mens Rea from Civil Recovery Forum:**
  - The engine strictly separates the Section 489-F criminal inquiry from civil forum determination.
  - **Rejection of Blanket Banking Court Routing:** Banking Courts established under the Financial Institutions (Recovery of Finances) Ordinance, 2001 (FIO) possess statutory jurisdiction under Section 9 **strictly over claims by or against a 'financial institution' arising from 'finance'** (Section 2(d) FIO).
  - Private commercial disputes between non-banking traders, companies, or individuals have zero connection to Banking Courts. Civil recovery in private commercial disputes lies exclusively before:
    * Ordinary Civil Courts under Section 9 CPC; or
    * Summary recovery suits under Order XXXVII of the Code of Civil Procedure, 1908 before District Courts or High Courts.
  - Forum selection is evaluated conditionally based on: (1) identity of parties (financial institution vs private entity); (2) nature of transaction (statutory finance vs commercial debt); and (3) cause of action.

---

#### 6. Contract 6: Enemy Property Custodian Authority, Statutory Adjudication & Appellate Remedies (Finding 9)
* **Primary Enactments & Statutory Framework:**
  1. *Enemy Property (Continuance of Emergency Provisions) Ordinance, 1969 (Ordinance I of 1969)*:
     - Contains **exactly seven numbered sections**: Section 1 (short title/extent), Section 2 (continuance of Defence of Pakistan Rules provisions), Section 3 (effect inconsistent with other enactments), Section 4 (delegations), Section 5 (savings), Section 6 (power to give effect), Section 7 (penalties).
     - **Sections 14 and 16 do not exist in Ordinance I of 1969.**
  2. *Defence of Pakistan Rules (1965)*, continued by Ordinance I of 1969:
     - **Rule 182** empowers the Central Government to take measures for the custody and preservation of enemy property.
  3. *Enemy Property (Custody and Registration) Order, 1965* (S.R.O. 111(R)/65):
     - Clause 4 vests all enemy property in the Custodian of Enemy Property for Pakistan.
     - Clause 5 governs management and administration.
* **Executive Nature of the Custodian:**
  - The Custodian is an executive officer appointed by and acting under the administrative control and policy directives of the Central / Federal Government (Ministry of Commerce).
  - The Custodian exercises executive and managerial functions, **not judicial functions of an Administrative Court or Tribunal**.
* **Appellate & Supervisory Authority:**
  - The emergency enactments provide for internal **administrative representations and departmental review** to the Federal Government against Custodian orders.
  - **No statutory judicial appellate tribunal exists under the 1969 Ordinance or 1965 Order.**
  - Parliament has never enacted legislation establishing an Administrative Court or Judicial Tribunal under Article 212(1)(c) of the Constitution.
* **Judicial Review & Civil Remedies (*Said Omar*, `PLD 1980 SC 158`; *Hoshang M. Dastur*, `PLD 1977 Kar 377`):**
  - Because no Article 212 judicial tribunal exists, Article 212(2) constitutional ouster does NOT apply to Custodian decisions:
    1. *Constitutional Review (Article 199):* High Courts entertain writ petitions challenging Custodian or Federal Government orders passed without lawful authority, in excess of jurisdiction, or in breach of natural justice.
    2. *Plenary Civil Suits (Section 9 CPC):* Civil Courts retain jurisdiction to adjudicate pre-existing private title and whether the property was lawfully enemy property at the vesting date.
* **Resulting Output State:**  
  `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES; ENEMY_PROPERTY_CUSTODIAN_EXECUTIVE_JURISDICTION; JUDICIAL_REVIEW_UNDER_ART_199_AND_CIVIL_SUIT_S9_MAINTAINABLE_ON_JURISDICTIONAL_DEFECTS`.

---

### 2.3 Traceable 30-Row Primary-Source to Requirement Mapping Table

| Criteria ID | Scope of Requirement | Controlling Primary Source & Citation | Exact Provision & Pin-Cite | Official Publication Baseline | Amendment Currency (Nov 1, 2026) | Authenticated Proposition & Target / Contractual Metric | Strict Evidentiary Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Gate interface contract v1.7.5 | Code of Civil Procedure, 1908 (Act V of 1908); Legal Practice | S.9 CPC; General Administrative Law | Pakistan Code, Vol. V | In force as amended | Domain gating interface strictly partitions legal records into deterministic ranking tiers without mutating production schema. | TEST_SPECIFIED |
| **AC-02** | Domain classification fixtures | West Pakistan Family Courts Act, 1964; Muslim Family Laws Ord. 1961 | S.5 & Sched., 1964 Act; *Shamim Akhtar*, 2015 SCMR 869 | Pakistan Code, Vol. XIV; SCMR 2015 | In force as amended | Dower and marriage dissolution claims belong exclusively to Family Court under S.5; segregated from civil suit queries. | TEST_SPECIFIED |
| **AC-03** | Statutory fallback 5-stage order | General Clauses Act, 1897; Interpretation of Statutes | Ss. 3(17), 27 GCA 1897; *Zia-ur-Rehman*, PLD 1973 SC 49 | Pakistan Code, Vol. III; PLD 1973 SC | In force | 5-stage fallback: direct match -> secondary statute -> foreign law exclusion -> procedural baseline -> ambiguous drop. | TEST_SPECIFIED |
| **AC-04** | Interdisciplinary doctrine contracts | CPC 1908; PPC 1860; CrPC 1898; Limitation Act 1908; Benami Act 2017; FIO 2001 | S.9 CPC; Ss.406, 420, 489-F PPC; Art 120 Limitation; S.2(8) Benami | Pakistan Code, Vols. I-XVIII; Gazettes | All in force as amended | Positive doctrine candidates admitted to Bucket 1B (`APPROVED_CROSS_DOMAIN`); negative demoted to Bucket 3. | TEST_SPECIFIED |
| **AC-05** | Unconditional Quarantine boundary (Pre-RRF) | Electronic Transactions Ordinance, 2002; High Court Rules & Orders | S.2(h) ETO 2002; Universal Quarantine Protocol | Pakistan Code, Vol. XV; HC Rules | In force | `is_quarantined=True` hard-dropped at Step 2 pre-RRF. QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER. Candidate never enters RRF, scoring, or generation. | TEST_SPECIFIED |
| **AC-06** | Strict mode generation boundary | Constitution of Pakistan, 1973; Legal Ethics Rules | Art 199 Constitution; Canons of Professional Conduct | Pakistan Code, Vol. XVI; PBC Rules | In force | Generation context strictly excludes Bucket 3 even if `strict_mode=False`. Off-domain records exposed in telemetry only. | TEST_SPECIFIED |
| **AC-07** | Authority hierarchy (Amended Art 189) | Constitution (27th Amendment) Act, 2025; Constitution 1973 | Art 189 (27th Amend); *Multiline*, 1995 SCMR 362 | Gazette of Pakistan, Ext., 2025; SCMR 1995 | In force as amended | FCC ratio binds SC on questions/principles decided. Missing nexus $\rightarrow$ non-controlling. Co-equal conflicts resolved via typed unresolved states. | TEST_SPECIFIED |
| **AC-08** | Pure relevance floor ($S_{\text{rerank}} \ge 0.35$) | Information Retrieval & Reranking Standards | Step 3 Context Assembly Contract; Calibration | System Technical Specifications | Current | Candidate below calibrated floor ($S_{\text{rerank}} < 0.35$) excluded from context assembly as `BELOW_RELEVANCE_FLOOR`. | TEST_SPECIFIED |
| **AC-09** | Canonical appeal deduplication | Code of Civil Procedure, 1908; Supreme Court Rules, 1980 | Order XLIII CPC; Order XV Supreme Court Rules 1980 | Pakistan Code, Vol. V; Supreme Court Rules | In force | Multiple law report citations of identical judicial appeal merged into canonical record preserving highest score. | TEST_SPECIFIED |
| **AC-10** | Native generation tokenizer contract | OpenAI API Documentation; Google Generative AI Docs | OpenAI `tiktoken==0.7.0` (`o200k_base`); Google GenAI API | PyPI tiktoken 0.7.0; Google Cloud GenAI SDK | Current stable (deprecated models excluded) | Execution of Native Tokenizer is a mandatory hard precondition. If offline/unavailable, aborts with `TOKENIZER_UNAVAILABLE_ABORT`. | TEST_SPECIFIED |
| **AC-11** | Atomic passage assembly & output cap | Model Context Envelope Specs; Legal Text Integrity Rules | Application Envelope $W_{\text{operational}}=8,000$; Output Cap $T_{\text{completion}}=1,000$ | Production Model Deployment Contract | Current | Complete serialized request counted; provider output cap enforced; atomic passages fit completely or dropped entirely. | TEST_SPECIFIED |
| **AC-12** | Gold-standard benchmark evaluator | Pakistani Legal Information Retrieval Standard | Evaluation Ground Truth Protocol; Benchmark Spec | Evaluation Harness Specs | Current | Benchmark evaluator scores Bucket 1B approved cross-domain precedents as relevant without false contamination penalty. | TEST_SPECIFIED |
| **AC-13** | Retrieval Quality (Macro-Recall@10) | Benchmark Evaluation Metric Standards | Macro-Averaged Recall@10 Formula; Non-Empty Gold Sets ($|\text{Gold}_q| \ge 1$) | Legal Information Retrieval Benchmark Protocol | Current | **Contractual Acceptance Target: Macro-Recall@10 = 100.0%, HitRate@10 = 100.0%**. Empirical Verification: 0/30 executed. | GATED_LIVE_PIPELINE |
| **AC-14** | Contamination Bound (Option A) | Benchmark Evaluation Metric Standards | Option A Fixed Denominator Protocol ($N_{\text{evaluated}}=150$); Threshold $\le 5/150$ | Benchmark Contamination Protocol | Current | **Contractual Acceptance Target: Contamination $\le 5/150 \approx 3.333\%$**. Empirical Verification: 0/30 executed. | GATED_LIVE_PIPELINE |
| **AC-15** | Legacy regression suite preservation | Repository Engineering Test Contract | 11 Pytest Regression Test Modules (`test_cross_encoder_reranker.py`, etc.) | Git Commit `feat/phase4-step1-planner` | **102 passed, 6 warnings in 34.28s (Exit code 0)** | Zero regression against existing retrieval and planner test suite. Confirmed passing. | **TEST_EXECUTED (100% Passed)** |
| **AC-16** | Traceable candidate audit trail | Administrative Law; Algorithmic Transparency | Step 15 Telemetry Contract; Candidate Provenance | Technical System Specification | Current | Every evaluated candidate emitted in diagnostic telemetry with explicit, traceable inclusion/exclusion reason. | TEST_SPECIFIED |
| **AC-17** | Article 212(1)(a) service conditions | Constitution of Pakistan, 1973; Service Tribunals Act, 1973 | Art 212(1)(a) Constitution; S.4 FST Act 1973; `2025 SCMR 134` | Pakistan Code, Vols. XVI & XVII; SCMR 2025 | In force as amended | Civil servant challenging terms/conditions barred under Art 212(2); FST exclusive. Contractor: `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`. | TEST_SPECIFIED |
| **AC-18** | Article 212(1)(b) public torts competence | Constitution of Pakistan, 1973; Code of Civil Procedure, 1908 | Art 212(1)(b) Constitution; Ss.9, 80(1), 80(2) CPC 1908; Enactment Search | Pakistan Code, Vols. V & XVI | In force | Enactment search shows no tribunal. Output: `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH`. Evaluated under S.9 CPC, indemnity, and authentic S.80 notice. Indian S.80(2) leave rejected. | TEST_SPECIFIED |
| **AC-19** | Article 212(1)(c) enemy property | Constitution of Pakistan, 1973; Enemy Property Ordinance, 1969 | Art 212(1)(c) Constitution; Ordinance I of 1969; Rule 182 DPR 1965 | Pakistan Code, Vol. XVI; Ordinance I of 1969 | In force | 1969 Ordinance establishes an executive Custodian, not an Art 212(1)(c) judicial tribunal. Returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES; JUDICIAL_REVIEW_MAINTAINABLE`. | TEST_SPECIFIED |
| **AC-20** | Article 212(2) provincial proviso | Constitution of Pakistan, 1973; Provincial Service Tribunals Acts | Art 212(2) Proviso; Punjab PST 1974; Sindh SST 1973 | Pakistan Code, Vol. XVI; Provincial Codes | In force | Art 212(2) ouster extends to PSTs only where Provincial Assembly resolution and parliamentary extension Act are enacted; otherwise provincial law. | TEST_SPECIFIED |
| **AC-21** | Residuary Article 120 inheritance | Limitation Act, 1908 (Act IX of 1908) | Arts 91, 92, 95, 120 Limitation Act 1908; *Saadat Khan*, PLD 2023 SC 362 | Pakistan Code, Vol. V; PLD 2023 SC 362 | In force as amended | Specific articles (91, 92, 95, 142) must be exhausted first. Residuary Art 120 (6 yrs) runs from unequivocal denial (Date $D$). Facts underspecified -> `LIMITATION_ARTICLE_UNRESOLVED`. | TEST_SPECIFIED |
| **AC-22** | Article 142 dispossession & ouster | Limitation Act, 1908; Limitation (Amendment) Act, 1995 | Art 142 Limitation Act 1908; *Ghulam Ali*, PLD 1990 SC 1 | Pakistan Code, Vol. V; Gazette 1995; PLD 1990 SC | In force as amended | Art 142 requires prior physical possession and actual ouster. Co-heir possession is joint; mutation is not dispossession. Art 144 omitted by Act II of 1995. | TEST_SPECIFIED |
| **AC-23** | Section 18 statutory fraud | Limitation Act, 1908 (Act IX of 1908) | Section 18 Limitation Act 1908 | Pakistan Code, Vol. V | In force as amended | Time runs from discovery upon affirmative proof of fraudulent concealment of right/document. Bare non-communication of mutation fails S.18. | TEST_SPECIFIED |
| **AC-24** | Authentic Section 2(8) Benami tree | Benami Transactions (Prohibition) Act, 2017 (Act VIII of 2017) | Section 2(8)(A)-(D), Ss. 3, 4, 5, 24, 25, 51; `2023 SCMR 572` | Gazette of Pakistan, Ext., 2017; SCMR 2023 | In force as amended | Independent limbs (A)-(D); exact exceptions (b)(i) [5-predicate generalized fiduciary] and (b)(ii) [family]; full fixtures with 5-step test ($P \ne H$). S.24 order $\rightarrow$ `BENAMI_TRANSACTION_ADJUDICATED`. | TEST_SPECIFIED |
| **AC-25** | Section 489-F mens rea at issuance & forum | Pakistan Penal Code; FIO 2001; Code of Civil Procedure, 1908 | S.489-F PPC; Ss.2(d), 9 FIO 2001; S.9/Order XXXVII CPC; `2010 SCMR 806` | Pakistan Code, Vols. I, V & XVII; SCMR 2010 | In force as amended | Mens rea evaluated at cheque issuance. Security label does not prevent S.489-F if debt existed. Liquidity failure is evidentiary. Banking Court requires FI and finance; private recovery in Civil Court. | TEST_SPECIFIED |
| **AC-26** | Section 420 inception-intention test | Pakistan Penal Code (Act XLV of 1860) | Ss. 415, 420 PPC; `1999 SCMR 1214`; `PLD 2005 SC 470` | Pakistan Code, Vol. I; SCMR 1999; PLD 2005 SC | In force as amended | S.420 requires dishonest intention at the time of representation/inducement. Commercial breach without inception fraud cannot be criminalized. FIR quashment in Bucket 1B. | TEST_SPECIFIED |
| **AC-27** | Section 406 entrustment vs debt | Pakistan Penal Code (Act XLV of 1860) | Ss. 405, 406 PPC; `PLD 2004 SC 460`; `2000 SCMR 445` | Pakistan Code, Vol. I; PLD 2004 SC; SCMR 2000 | In force as amended | S.406 requires entrustment in fiduciary capacity. Sale on credit creates debtor-creditor relationship; failure to pay is civil debt, not criminal breach of trust. | TEST_SPECIFIED |
| **AC-28** | Amended Art 189 precedent binding ratio | Constitution (27th Amendment) Act, 2025; Constitution 1973 | Article 189 Constitution; *Multiline Associates*, 1995 SCMR 362 | Gazette of Pakistan, Ext., 2025; SCMR 1995 | In force as amended | FCC ratio binds SC on questions/principles decided. Missing nexus $\rightarrow$ non-controlling. Historical SC ruling displaced only to extent of direct conflict (`PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT`). | TEST_SPECIFIED |
| **AC-29** | Deployed request recount & atomic truncation | Production Deployment Specs; OpenAI & Google API Specs | Application Envelope $W_{\text{operational}}=8,000$; `gpt-4o-2024-11-20` / `gemini-2.5-pro` | Official API Documentation | Current supported models | Complete serialized request counted; native tokenizer enforced; atomic passage assembly prevents partial citations; non-ASCII Urdu verified. | TEST_SPECIFIED |
| **AC-30** | Benchmark dual-denominator & ground-truth | Legal Information Retrieval Benchmark Standards | Option A Fixed Denominator ($N_{\text{evaluated}}=150$); Ground Truth Mapping | Evaluation Benchmark Suite (Commit `7378557`) | Current | **Contractual Acceptance Protocol: 30 queries, top-10 Recall@10 = 100%, top-5 Contamination $\le 5/150$**. Baseline artifacts hashed & committed. Empirical Verification: 0/30 executed. | GATED_LIVE_PIPELINE |

---

## 3. Constitutional & Precedential Hierarchy Verification

### 3.1 Twenty-Seventh Constitutional Amendment (2025) & Operative Article 189
Under Pakistan's **Constitution (Twenty-Seventh Amendment) Act, 2025**, Article 189 was substituted:
> *(1) Any decision of the Federal Constitutional Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan, including the Supreme Court.*  
> *(2) Subject to clause (1), any decision of the Supreme Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan.*

### 3.2 Nuanced Seven-Rule Precedential Resolution Engine

1. **Rule 1 (Institutional Apex Dominance Across Tiers):**
   - Decisions of the Federal Constitutional Court (FCC) deciding a question of law or enunciating a principle of law bind all other courts in Pakistan, including the Supreme Court.
   - Institutional apex authority strictly controls across tiers. An SC decision—even by a larger bench of 7, 9, or 11 judges—cannot overrule an FCC decision deciding that question of law.
2. **Rule 2 (Material Nexus Requirement & Distinguishing Obiter Dicta):**
   - The engine evaluates whether the FCC decision actually decided the specific question of law (*ratio decidendi*) governing the instant query.
   - *Lack of Nexus:* If an FCC decision determines an issue lacking material nexus to the query (e.g. an FCC ruling on constitutional delimitation cited in a private property partition), it is classified as `NON_CONTROLLING_DUE_TO_ABSENCE_OF_NEXUS`.
   - *Obiter Dicta Separation:* Incidental judicial observations (*obiter dicta*) carry high persuasive value but do not create an irreconcilable conflict under Article 189 (*Said Omar*, `PLD 1980 SC 158`). Returns `PERSUASIVE_OBITER_NOT_BINDING_RATIO`.
   - *Independent SC Precedent Evaluation:* An SC decision controls in such a case **only if it independently supplies an applicable legal ratio directly on point**, not by virtue of displacing the FCC decision.
3. **Rule 3 (Factual & Statutory Context Differentiation):**
   - If two decisions arise under materially distinguishable statutory schemes (e.g. pre-amendment vs post-amendment statute, or civil suit under CPC vs summary eviction under rent laws), the engine distinguishes them on statutory context.
   - Returns typed state: `DISTINGUISHED_ON_STATUTORY_CONTEXT`, preventing artificial conflict escalation.
4. **Rule 4 (Intra-Court Bench Strength — Common-Law Basis of *Multiline Associates*):**
   - The rule in *Multiline Associates v. Arshad Luqman* (`1995 SCMR 362`) is rooted in foundational common-law principles of judicial discipline (*stare decisis* and institutional integrity).
   - This principle applies symmetrically to both apex institutions:
     * Within the Supreme Court: SC 5-judge bench binds SC 3-judge bench, regardless of decision date.
     * Within the Federal Constitutional Court: FCC larger bench binds FCC smaller bench.
5. **Rule 5 (Conflicting Co-Equal Benches & Strict Prohibition on Date-Based Overruling):**
   - Under *Multiline Associates* (`1995 SCMR 362`, p. 378), a coordinate bench cannot overrule another coordinate bench of equal strength.
   - **Strict Prohibition on Automatic Recency Resolution:** The engine is **strictly forbidden from resolving co-equal apex conflicts by choosing the more recent date or law report volume**.
   - *Co-Equal Supreme Court Conflict:* When two co-equal SC benches (e.g. 3-judge vs 3-judge) express conflicting ratios on the same statutory question, the engine emits both competing authorities in the ranking list with diagnostic tags and returns `UNRESOLVED_CO_EQUAL_APEX_CONFLICT`.
   - *Co-Equal FCC Conflict:* When two co-equal FCC benches express conflicting ratios on the same constitutional or legal question, the engine emits both authorities and returns `UNRESOLVED_CO_EQUAL_FCC_CONFLICT`.
   - Telemetry records that authoritative resolution requires constitution of a larger bench by the respective Chief Justice.
6. **Rule 6 (Historical Decisions & Partial Displacement Semantics — Finding 12):**
   - A post-amendment FCC decision **does not globally erase or delete** earlier Supreme Court judgments from repository history.
   - The engine evaluates:
     * (a) Identity of Legal Question: Did the FCC directly adjudicate the identical question of law?
     * (b) Binding Ratio: Is the FCC holding an operative ratio decidendi?
     * (c) Scope of Displacement: The earlier Supreme Court authority is displaced **strictly to the extent of direct, irreconcilable conflict** on that legal point. Output: `PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT`.
     * (d) Residual Precedential Authority: Any distinct legal propositions, procedural principles, or statutory constructions in the historical SC decision not directly addressed by the FCC remain binding law under Article 189(2) and constitutional continuity principles (Articles 264 and 268). Both authorities are emitted with explicit relationship metadata.
7. **Rule 7 (Apex Scope Conflict Escalation):**
   - When the substantive scope, ratio, or applicability of competing apex authorities cannot be reliably reconciled through statutory distinction, the engine returns `UNRESOLVED_APEX_RATIO_SCOPE`.

---

## 4. Tokenizer Architecture & Legacy-Vector Dual-Mode Filtering Contract

### 4.1 Supported Production Deployments & Lifecycle Records (November 2026 Baseline)
The engine pins supported production runtime envelopes and model-specific invocation parameters:

| Component | Primary Production Deployment | Secondary / Failover Deployment |
| :--- | :--- | :--- |
| **Model Identifier** | `gpt-4o-2024-11-20` (Pinned Supported Snapshot) | `gemini-2.5-pro` (Active Flagship Flag) |
| **Model Provider** | OpenAI API | Google Generative AI API |
| **Provider Context Limit ($W_{\text{physical}}$)** | $128,000\text{ tokens}$ | $1,000,000\text{ tokens}$ |
| **Application Operational Ceiling ($W_{\text{operational}}$)** | **$8,000\text{ tokens}$** (Application-Enforced Limit) | **$8,000\text{ tokens}$** (Application-Enforced Limit) |
| **Maximum Generation Output ($T_{\text{completion}}$)** | **$1,000\text{ tokens}$** (Hard Enforced Parameter) | **$1,000\text{ tokens}$** (Hard Enforced Parameter) |
| **API Output Cap Parameter Name** | `max_tokens = 1000` | `config = {"max_output_tokens": 1000}` |
| **API Endpoint Path** | `/v1/chat/completions` | `/v1beta/models/gemini-2.5-pro:generateContent` |
| **Native Tokenizer Implementation** | `tiktoken==0.7.0` (Pinned, `o200k_base` encoding) | `google.genai.models.count_tokens` (Native API) |
| **Model Lifecycle Status** | Active (Deprecated snapshot `2024-08-06` avoided) | Active (Retired `1.5-pro-002` permanently removed) |

### 4.2 Application Budget Envelope Invariant
$$T_{\text{prompt}} \le 7,000\text{ tokens}$$
$$T_{\text{completion}} \le 1,000\text{ tokens}$$
$$W_{\text{operational}} = 8,000\text{ tokens} \ll W_{\text{physical}}$$
$$\therefore T_{\text{prompt}} + T_{\text{completion}} \le 7,000 + 1,000 = 8,000 = W_{\text{operational}}$$

* **Operational Envelope Definition:** The 8,000-token limit is an **application-enforced conservative budget envelope** designed to guarantee rapid response latency, strict inference cost ceilings, and predictable generation performance, well within the physical context windows ($128\text{k} / 1\text{M}$).
* **Hard API Output Parameter:** Generation call explicitly passes provider-specific output limits (`max_tokens=1000` for OpenAI; `max_output_tokens=1000` for Gemini), physically bounding downstream model generation to 1,000 tokens.
* **Complete Request Overhead Accounting:** $T_{\text{fixed}}$ measures the complete serialized prompt payload, including JSON/XML message framing (`role`, `content`, message delimiters), tool definitions (if enabled), and XML wrappers (`<system_instructions>`, `<query_plan>`, `<user_query>`).
* **Concatenation Anomaly Prevention (Mandatory Post-Assembly Recount):** Because sub-word BPE tokenization can merge characters across string concatenation boundaries ($T(A) + T(B) \ne T(A + B)$), a **mandatory recount of the complete concatenated serialized prompt** is executed before dispatch. If $T_{\text{final}} > 7,000$, the engine fails closed with `FAIL_CLOSED_PAYLOAD_EXCEEDED` and drops trailing candidates until $T_{\text{final}} \le 7,000$.

### 4.3 Atomic Legal-Passage Assembly & Truncation Invariant
* **Atomic Unit Definition:** To guarantee legal-context integrity, a legal text block is defined as an **indivisible atomic unit**:
  - A statutory section with its complete sub-sections, provisos, and explanations; or
  - A judicial headnote/holding with its citation, ratio, and qualifying conditions.
* **Indivisibility Rule:** The engine **strictly forbids intra-passage truncation** (e.g. separating a statutory section from its qualifying proviso, or separating a judgment ratio from its distinguishing facts).
* **Budget Overflow Action:** If an entire atomic legal block cannot fit within the remaining candidate margin ($\Delta = 7,000 - (T_{\text{fixed}} + T_{\text{cands}})$), the engine **drops the entire atomic unit** and logs `ATOMIC_BLOCK_BUDGET_OVERFLOW`. It never emits a half-severed citation or partial proviso.
* **Safe Abort:** Execution of the Native Tokenizer is a mandatory hard precondition. If offline/unavailable, returns typed `TOKENIZER_UNAVAILABLE_ABORT` and halts context assembly safely. Non-ASCII ratio $> 15\%$ without native tokenizer returns `FAIL_CLOSED_NON_ASCII_OVERFLOW`.

### 4.4 Unconditional Hard Quarantine Invariant & Strict Pipeline Isolation (Finding 17 / AUTH-07)
* **Invariant:** `QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER`.
* **Hard Pre-RRF Boundary & Diagnostic Audit Pool Separation:**
  ```python
  # Step 2: Unconditional Hard Quarantine Boundary (Pre-RRF)
  if candidate.is_quarantined:
      candidate.exclusion_reason = "IS_QUARANTINED"
      dropped_pool.append(candidate)
      continue  # NEVER enters ranking, scoring, reciprocal rank fusion, or context assembly
  ```
* **Strict Pipeline Separation from Bucket 2:**
  - Bucket 2 (`SECONDARY_AUTHORITY`) is exclusively reserved for non-quarantined secondary or ambiguous candidates (e.g., procedural baseline records or candidates requiring diagnostic review).
  - A quarantined candidate **NEVER** enters Bucket 2.
  - A quarantined candidate **NEVER** enters candidate scoring, Reciprocal Rank Fusion (RRF), ranking input, or LLM generation context.
* **Executable Verification Assertions (Across both `strict_mode=True` and `strict_mode=False`):**
  - `assert quarantined_candidate not in rrf_input`
  - `assert quarantined_candidate not in candidate_scoring_input`
  - `assert quarantined_candidate not in ranking_input`
  - `assert quarantined_candidate not in generation_context`
  - `assert quarantined_candidate in dropped_pool` with `quarantined_candidate.exclusion_reason == "IS_QUARANTINED"`
* **Strict Mode Insulation:** The `strict_mode` parameter (True/False) controls admission of secondary candidates into diagnostic telemetry, but **can NEVER revive, un-drop, or make eligible a quarantined candidate**. If a candidate has `is_quarantined=True`, it is discarded unconditionally.

### 4.5 Legacy Vector Compatibility & Deterministic Heuristic Scoring Contract (Finding 18 / AUTH-04)
To eliminate the severe recall regression risk identified in the repository audit (where ~401,351 existing Pinecone vectors lack legal-domain metadata):
* **Strict Prohibition on Upstream Dense Metadata Filtering:** Hard metadata filters (e.g. `filter={"domain": {"$in": ...}}`) are **strictly prohibited on raw Pinecone vector queries**. Passing a hard metadata filter against an index where legacy vectors lack domain metadata causes dense retrieval recall to collapse from $0.467$ to $0.000$.
* **Five-Tier Domain Provenance Taxonomy:**
  1. `VERIFIED_METADATA`: Explicit, validated domain tag attached to candidate from verified database source.
  2. `INFERRED_ON_DOMAIN`: Domain inferred via deterministic statutory index matching primary subject matter to target query domain with heuristic score $S_{\text{heur}} \ge 0.85$. Admitted to Bucket 1A.
  3. `INFERRED_CROSS_DOMAIN`: Domain inferred to belong to an authenticated cross-domain doctrine (e.g. S.489-F PPC civil debt, S.420 inception fraud) with $S_{\text{heur}} \ge 0.85$. Admitted to Bucket 1B.
  4. `AMBIGUOUS_DOMAIN_QUARANTINE_SAFE`: Candidate has ambiguous or conflicting statutory citations ($0.50 \le S_{\text{heur}} < 0.85$); routed to Bucket 2 (SECONDARY_AUTHORITY) for diagnostic review; strictly excluded from LLM generation context in all modes.
  5. `DOMAIN_INFERENCE_FAILED`: Candidate lacks statutory citations, has uncalibrated score ($S_{\text{heur}} < 0.50$), or contains unrecognizable text; fails closed and is abstained from inference; dropped from generation context as `INFERENCE_ABSTAIN_EXCLUDED`.
* **Deterministic Heuristic Scoring Formula ($S_{\text{heur}}$):**
  To maintain strict scientific honesty and avoid unfounded claims of empirical probability calibration, the domain confidence score is formally designated and computed as a deterministic heuristic score:
  $$S_{\text{heur}} = w_{\text{statute}} \cdot \mathbb{I}(\text{statute\_match}) + w_{\text{section}} \cdot \mathbb{I}(\text{section\_match}) + w_{\text{kw}} \cdot \text{keyword\_overlap}$$
  where:
  - $w_{\text{statute}} = 0.50$ (matching primary enactment name against `pakistan_statute_index_v1.json`);
  - $w_{\text{section}} = 0.35$ (matching specific statutory section or schedule article);
  - $w_{\text{kw}} = 0.15$ (normalized legal terminology overlap).
* **Authoritative Statutory Index & Normalized Citation Parser:**
  - Uses versioned statutory index (`pakistan_statute_index_v1.json`).
  - Standardized parser normalizes citation tokens (e.g., `S. 420 PPC`, `Order XXXVII CPC`, `S. 5 Family Courts Act 1964`, `S. 2(8) Benami Act 2017`).
  - Separates primary statutory subject matter from incidental/boilerplate citations (e.g., general references to S.151 CPC inherent powers, General Clauses Act 1897 provisions, or general procedural orders).
* **Fail-Closed Abstention Contract:** If $S_{\text{heur}} < 0.50$, the engine **abstains from making an inference**, returns `DOMAIN_INFERENCE_FAILED`, and drops the candidate from the LLM prompt payload with exclusion code `INFERENCE_ABSTAIN_EXCLUDED`.
* **Auditability Invariant:** Inferred domain is never written to the source database or represented as verified metadata; it is emitted strictly in diagnostic telemetry with raw heuristic score and statutory matched tokens.
* **Zero Production Index Modifications:** Legacy vectors are preserved untouched in Pinecone without unverified backfilling or vector deletions.

---

## 5. Disaggregated Retrieval Quality & Option A (Fixed Denominator) Benchmark Protocol

The benchmark harness enforces exact, independent definitions and adopts **Option A (Fixed Denominator)** to guarantee absolute mathematical reproducibility:

### 5.1 Macro-Averaged Recall@10 (AC-13, AUTH-05)
* **Measurement Population:** Query-level evaluation across all $N_{\text{queries}} = 30$ standardized benchmark queries (`legal_retrieval_test_cases.json`).
* **Evaluation Depth ($K=10$):** Recall evaluates the **top-10 candidate pool** returned to the reranker and orchestrator, measuring retrieval coverage and capacity to capture all relevant primary authorities.
* **Gold-Standard Set Requirement:** Every query $q$ must possess an authenticated, non-empty set of relevant primary legal authorities: $|\text{Gold}_q| \ge 1$.
* **Per-Query Recall Formulation:**
  $$\text{Recall@10}_q = \frac{|\text{Gold}_q \cap \text{Top10}_q|}{|\text{Gold}_q|}$$
* **Macro-Averaged Metric (Contractual Acceptance Target = 100.0%):**
  $$\text{Macro-Recall@10} = \frac{1}{30} \sum_{q=1}^{30} \text{Recall@10}_q = 100.0\% \quad \text{(Target Standard)}$$
* **Distinct Hit Rate@10 Metric (Contractual Acceptance Target = 100.0%):**
  $$\text{HitRate@10} = \frac{1}{30} \sum_{q=1}^{30} \mathbb{I}(|\text{Gold}_q \cap \text{Top10}_q| \ge 1) = 100.0\% \quad \text{(Target Standard)}$$
* **Current Empirical Verification Status:** **`GATED_LIVE_PIPELINE` — 0 / 30 queries executed under v1.7.5** (Pending Implementation Authorization).

### 5.2 Option A (Fixed Denominator) Contamination Protocol (AC-14, AUTH-05, AUTH-06)
* **Rationale for Top-5 Measurement ($K=5$):**
  - While retrieval depth is evaluated at $K=10$, prompt generation payload assembly consumes the **top-5 post-gating candidates**.
  - Contamination is therefore evaluated strictly across the top-5 candidate positions that could actually populate the LLM generation context window.
* **Evaluated Candidate Positions:** Candidates occupying positions $k \in \{1 \dots 5\}$ **after domain gating admission** (Bucket 1A + Bucket 1B).
* **Quarantine Enforcement:** Candidates marked `is_quarantined=True` are dropped at Step 2 (pre-RRF). If a quarantined candidate leaks into the evaluated top-5 positions, the benchmark fails immediately with fatal violation `QUARANTINE_LEAKAGE_FAILURE`.
* **Interdisciplinary Relevance Standard (AUTH-06):** Relevance is judged against manually reviewed multi-domain gold labels (`legal_retrieval_test_cases.json`). Precedents from intersecting legal domains recognized under approved cross-domain doctrines (e.g. S.489-F PPC civil debt, S.420 inception fraud, female inheritance joint possession) are recognized as relevant primary authorities and **never penalized as contamination**.
* **Fixed Population Requirement:** Every query $q \in \{1 \dots 30\}$ is strictly required to return at least 5 candidates in its evaluated set. If any query returns fewer than 5 candidates, the benchmark halts immediately with failure code `BENCHMARK_INSUFFICIENT_CANDIDATES`.
* **Exact Evaluated Denominator ($N_{\text{evaluated}}$):**
  $$N_{\text{evaluated}} = 30 \text{ queries} \times 5 \text{ positions} = 150 \text{ positions strictly}$$
* **Exact Contamination Formulation (Contractual Acceptance Ceiling $\le 5/150$):**
  $$\text{Contamination Rate} = \frac{\sum_{q=1}^{30} \sum_{k=1}^{5} \mathbb{I}(c_{q,k} \in \text{OffDomainPool})}{150} \le \frac{5}{150} = \frac{1}{30} \approx 3.333\% \quad \text{(Target Standard)}$$
  - Maximum permitted off-domain candidates across the entire benchmark is **strictly 5 positions out of 150**.
  - Any run with 6 or more off-domain candidates fails the benchmark.
* **Current Empirical Verification Status:** **`GATED_LIVE_PIPELINE` — 0 / 30 queries executed under v1.7.5** (Pending Implementation Authorization).

### 5.3 Verified Benchmark Artifact Provenance Manifest (Finding 20 / AUTH-05, AUTH-06)
To ensure absolute cryptographic reproducibility and prevent unversioned baseline drift, all non-production benchmark and evaluation artifacts have been committed to version control on branch `feat/phase4-step1-planner` (Commit `7378557`). Their authentic SHA-256 checksums are permanently recorded below:

| Artifact File Path | Git Tracked Commit | Cryptographic SHA-256 Checksum | Purpose / Content Description |
| :--- | :--- | :--- | :--- |
| `legal_retrieval_test_cases.json` | `7378557` | `DE73B781B786F5CB62A54A88D86018C2E9E3E77398D213076F8623AD813C42DD` | 30 standardized gold-standard legal test queries with verified relevant/cross-domain citations. |
| `scripts/run_retrieval_benchmark.py` | `7378557` | `18AA81B040E7D054A860C1177CC00347CBDE42A6BA000497C660DF73A0A039AD` | Reproducible benchmark execution harness evaluating Macro-Recall@10 and Option A Contamination. |
| `benchmark_metrics_summary.json` | `7378557` | `8602A62A150F39318D22EEDA8CDC74A3DB05333855A2584FC796AC0663E3135A` | Historical benchmark metrics summary baseline. |
| `retrieval_benchmark_results.csv` | `7378557` | `C4E32307FEBCC2F002A4C59292D4EA7832BDBB3AB01AC399E00CCB27D9864075` | Tabular query-level evaluation output records. |
| `LEGAL_RAG_EVALUATION_REPORT.md` | `7378557` | `B70454410E7C834675B416BFEEEDCE0B95E969CD7DF456444F2C071156ECF652` | Comprehensive pre-phase4 evaluation report on retrieval gaps. |
| `LEGAL_RAG_FAILURE_ANALYSIS.md` | `7378557` | `A298AB8FB7C21B20B7D0E9CB9F1716CD86A37EAAAFD061B6E16C0DF844881B16` | Diagnostic failure analysis across test cases. |
| `LEGAL_RAG_REPOSITORY_AUDIT.md` | `7378557` | `0BFB2CBCA4B8BF082A5B09827A7444A87FC76CE1CCB122FAD13E113DDA486831` | Deep repository audit identifying 401,351 legacy Pinecone vectors lacking domain metadata. |
| `LEGAL_RAG_TARGET_ARCHITECTURE.md` | `7378557` | `22F365644C5BC9E4206A636D60DEAEA847DC42A86585851701E72A27086E8945` | Target technical design specification for post-rerank domain gating. |

---

## 6. Pre-Authorization Matrix & Extended Acceptance Criteria Matrix

### 6.1 Pre-Authorization Tracking Matrix (AUTH-01 through AUTH-10)

| ID | Required Pre-Authorization Condition | Architectural Specification & Contract Rule | Evidentiary Status in v1.7.5 |
| :--- | :--- | :--- | :--- |
| **AUTH-01** | Correct Benami fixtures | 5-step statutory identity test ($P \ne H$); 5-predicate generalized fiduciary evaluation (`FIDUCIARY_CAPACITY_ESTABLISHED`, `RECOGNIZED_FIDUCIARY_ROLE`, `PROPERTY_HELD_IN_THAT_FIDUCIARY_CAPACITY`, `BENEFIT_RELATIONSHIP_ESTABLISHED`, `STATUTORY_EXCEPTION_ESTABLISHED`); non-agent fiduciaries (trustee, executor, director, legal adviser) and commercial agent holding on personal account. | **TEST_SPECIFIED** |
| **AUTH-02** | Article 212 completeness | Scoped finding `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH` across Federal and 4 Provinces; Custodian executive jurisdiction vs judicial review under Art 199 and S.9 CPC (*PLD 1980 SC 158*); four-step statutory-exclusion check (authentic S.80(1) notice, S.80(2) costs rule, 3-month WS proviso, indemnity clauses). Indian S.80(2) urgent-relief exception rejected (`REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2`). S.80 CPC strictly inapplicable to Art 199 writ. | **TEST_SPECIFIED** |
| **AUTH-03** | Apex precedent hierarchy | Nuanced 7-rule engine: FCC co-equal conflict (`UNRESOLVED_CO_EQUAL_FCC_CONFLICT`), SC co-equal conflict (`UNRESOLVED_CO_EQUAL_APEX_CONFLICT`), *Multiline Associates* common-law discipline, historical ruling partial displacement (`PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT`), ratio vs obiter distinction. | **TEST_SPECIFIED** |
| **AUTH-04** | Legacy vector compatibility | Prohibition on upstream Pinecone metadata filters; post-retrieval deterministic statutory domain inference for ~401,351 legacy vectors; 5-tier provenance taxonomy; deterministic heuristic scoring formula ($S_{\text{heur}}$) with fail-closed abstention ($S_{\text{heur}} < 0.50$); dense recall preserved. | **TEST_SPECIFIED** |
| **AUTH-05** | Benchmark contract | Exact Recall@10 ($K=10$, retrieval depth) and Contamination ($K=5$, generation payload) definitions; Option A fixed denominator ($N_{\text{evaluated}}=150$ strictly); `BENCHMARK_INSUFFICIENT_CANDIDATES` fail-closed halt; baseline artifacts hashed and tracked in git. | **TEST_SPECIFIED** |
| **AUTH-06** | Mixed-domain relevance | Manually reviewed multi-domain gold labels (`legal_retrieval_test_cases.json`, SHA-256 `DE73...`); recognized cross-domain doctrines (S.489-F, S.420, S.406, female inheritance) scored as relevant primary law without contamination penalty. | **TEST_SPECIFIED** |
| **AUTH-07** | Quarantine integrity | Step 2 pre-RRF hard drop; `QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER`. Absolute pipeline isolation: quarantined candidates never enter Bucket 2, candidate scoring, RRF, ranking input, or generation context across both `strict_mode=True` and `strict_mode=False`. | **TEST_SPECIFIED** |
| **AUTH-08** | Tokenizer & payload safety | Conservative envelope ($W_{\text{operational}}=8,000 \ll 128\text{k}/1\text{M}$); API output cap `max_tokens=1000`; pre-dispatch serialized recount; atomic legal passage indivisibility; non-ASCII Urdu boundary checks. | **TEST_SPECIFIED** |
| **AUTH-09** | Provider resilience | Simulated missing API credentials (`CREDENTIALS_MISSING_ABORT`), network timeouts (`GATEWAY_TIMEOUT_ABORT`), and Voyage embedding failure failover to lexical/BM25 search (`EMBEDDING_PROVIDER_FALLBACK`). | **TEST_SPECIFIED** |
| **AUTH-10** | Regression preservation | 11 Pytest legacy test modules executed in repository workspace with `$env:PYTHONPATH="."`. Baseline: **102 passed, 6 warnings in 34.28s (Exit code 0)**. Zero legacy regressions. | **TEST_EXECUTED (100% Passed)** |

---

### 6.2 Reconciliation of 10 Pipeline Engineering Conditions

| Engineering Condition | Pipeline Boundary & Architecture Rule | Mapped Criteria | Target Test Identifier |
| :--- | :--- | :--- | :--- |
| **1. `allowed_domains_filter` enforcement** | Domain gate validates candidate metadata against query-plan `target_domains`; unallowed domains excluded unless recognized under cross-domain doctrine. | **AC-01, AC-02** | `test_domain_classification_positive_negative` |
| **2. Legitimate interdisciplinary cases** | Bucket 1B (`APPROVED_CROSS_DOMAIN`) admits recognized interdisciplinary doctrines (S.489-F private recovery, S.420 inception fraud, family co-ownership). | **AC-04, AC-25, AC-26, AC-27** | `test_doctrine_contracts_positive_negative` |
| **3. Mixed-domain precedent preservation** | Judgments addressing intersecting civil and criminal remedies preserved via canonical appeal ID and multi-domain tagging; not dropped due to primary tag. | **AC-04, AC-09** | `test_canonical_appeal_deduplication` |
| **4. Quarantine before RRF integration** | Hard boundary at Step 2: candidates marked `is_quarantined=True` dropped immediately to `dropped_pool` BEFORE reciprocal rank fusion or reranking. Quarantined candidates never enter Bucket 2 or RRF. | **AC-05** | `test_quarantine_hard_drop_top_scoring` |
| **5. Explicit rejection/demotion telemetry** | Every non-admitted candidate receives an explicit, traceable enum reason code in telemetry (`IS_QUARANTINED`, `BELOW_RELEVANCE_FLOOR`, `ATOMIC_BLOCK_BUDGET_OVERFLOW`, `INFERENCE_ABSTAIN_EXCLUDED`). | **AC-16** | `test_candidate_audit_trail_telemetry` |
| **6. Strict mode generation boundary** | Generation context strictly excludes Bucket 3 off-domain candidates even if caller sets `strict_mode=False`. Off-domain records exposed in telemetry only. | **AC-06** | `test_strict_mode_generation_boundary` |
| **7. No unconditional Top-5/Top-10 truncation** | Context assembly dynamically governed by token budget and relevance floor ($S_{\text{rerank}} \ge 0.35$); naive list slicing (`candidates[:5]`) strictly prohibited. | **AC-08, AC-11** | `test_pure_relevance_floor_cutoff` |
| **8. Voyage fallback failure handling** | When dense embedding provider fails or times out, retrieval safely falls back to lexical / BM25 search with typed status `EMBEDDING_PROVIDER_FALLBACK`. | **AC-03, AC-10** | `test_voyage_fallback_lexical_resilience` |
| **9. Missing credentials & timeout tests** | Unit tests simulate missing API keys and network timeouts; engine fails closed safely with `CREDENTIALS_MISSING_ABORT` and `GATEWAY_TIMEOUT_ABORT`. | **AC-10, AC-29** | `test_native_tokenizer_contract_and_abort` |
| **10. Malformed response handling** | Incoming API payloads and response structures validated against Pydantic schemas; malformed payloads fail closed with `MALFORMED_PAYLOAD_ABORT`. | **AC-01, AC-29** | `test_native_tokenizer_full_payload_boundary` |

---

### 6.3 Extended Acceptance Criteria Matrix (AC-01 through AC-30)

| Criteria ID | Scope of Requirement | Target Test Identifier | Test Tier | Fixtures, Negative Conditions & Forum Logic | Expected Assertion & Result | Strict Evidentiary Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Gate interface contract v1.7.5 | `test_domain_gate_interface_contract` | Pure Unit | Valid candidate list + query plan passed to `partition_candidates_into_ranking_buckets()`. | Returns partitioned buckets; zero schema deviations; telemetry populated. | **TEST_SPECIFIED** |
| **AC-02** | Domain classification fixtures | `test_domain_classification_positive_negative` | Pure Unit | Synthetic on-domain civil case vs off-domain family dower case (`2015 SCMR 869`). | On-domain placed in Bucket 1A; off-domain placed in Bucket 3. | **TEST_SPECIFIED** |
| **AC-03** | Statutory fallback 5-stage order | `test_statutory_fallback_five_stage_order` | Pure Unit | Direct statute match, secondary safe statute, foreign statute, unannotated procedural, ambiguous. | Direct $\rightarrow$ 1A; Foreign $\rightarrow$ 3; Procedural $\rightarrow$ 2; Ambiguous $\rightarrow$ Dropped. | **TEST_SPECIFIED** |
| **AC-04** | Interdisciplinary doctrine contracts | `test_doctrine_contracts_positive_negative` | Pure Unit | 5 Positive fixtures (`2025 SCMR 134`, `1999 SCMR 1214`, `PLD 1990 SC 1`, `2023 SCMR 572`, `2010 SCMR 806`) + 5 Negative fixtures. | Positive admitted to Bucket 1B (`APPROVED_CROSS_DOMAIN`); Negative demoted to Bucket 3. | **TEST_SPECIFIED** |
| **AC-05** | Unconditional Quarantine boundary (Pre-RRF) | `test_quarantine_hard_drop_top_scoring` | Pure Unit | Candidate marked `is_quarantined=True` with highest cross-encoder score ($0.95$). Evaluated under both `strict_mode=True` and `strict_mode=False`. | Hard-dropped to `dropped_pool` before RRF. Assertions: `candidate not in rrf_input`, `candidate not in ranking_input`, `candidate not in generation_context`. Invariant: `QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER`. | **TEST_SPECIFIED** |
| **AC-06** | Strict mode generation boundary | `test_strict_mode_generation_boundary` | Pure Unit | Diagnostic caller sets `strict_mode=False`. | Bucket 3 candidates returned in telemetry only; strictly excluded from `assembled_context`. | **TEST_SPECIFIED** |
| **AC-07** | Authority hierarchy (Amended Art 189) | `test_constitutional_hierarchy_subject_matter` | Pure Unit | (a) FCC ruling on legal ratio vs SC ruling on same point; (b) FCC ruling lacking nexus; (c) Co-equal SC conflict; (d) Co-equal FCC conflict. | In (a), FCC ratio binds SC; in (b), SC controls only if on point; in (c), returns `UNRESOLVED_CO_EQUAL_APEX_CONFLICT`; in (d), returns `UNRESOLVED_CO_EQUAL_FCC_CONFLICT`. | **TEST_SPECIFIED** |
| **AC-08** | Pure relevance floor ($S_{\text{rerank}} \ge 0.35$) | `test_pure_relevance_floor_cutoff` | Pure Unit | Apex Supreme Court candidate with $S_{\text{rerank}} = 0.31 < 0.35$. | Excluded at Step 3 of context assembly; status `BELOW_RELEVANCE_FLOOR`. No unconditional slicing. | **TEST_SPECIFIED** |
| **AC-09** | Canonical appeal deduplication | `test_canonical_appeal_deduplication` | Pure Unit | Two records representing same judgment (Civil Appeal 801/2021) from different law reports. | Merged into single canonical record preserving highest score; distinct appeals preserved. | **TEST_SPECIFIED** |
| **AC-10** | Native generation tokenizer contract | `test_native_tokenizer_contract_and_abort` | Controlled Integration | Pinned `tiktoken==0.7.0` attached; simulated outage (`allow_unverified_fallback=False`). | Normal: returns `SUCCESS` exact count; Outage: returns `TOKENIZER_UNAVAILABLE_ABORT`. | **TEST_SPECIFIED** |
| **AC-11** | Atomic legal-passage assembly & output cap | `test_context_budget_enforcement_and_atomic_truncation` | Pure Unit | Payload with full XML framing, 10 legal candidates; oversized candidate exceeding remaining budget $\Delta$. | Recount enforces $T_{\text{prompt}} \le 7,000$; output capped at 1,000; oversized atomic block dropped (`ATOMIC_BLOCK_BUDGET_OVERFLOW`). | **TEST_SPECIFIED** |
| **AC-12** | Gold-standard benchmark evaluator | `test_benchmark_evaluator_doctrine_awareness` | Controlled Integration | Benchmark script runs over test fixtures with cross-domain doctrine candidates. | Evaluator correctly scores Bucket 1B candidates as relevant without false contamination. | **TEST_SPECIFIED** |
| **AC-13** | Retrieval Quality (Macro-Recall@10) | `test_live_benchmark_recall` | Live Pipeline | 30 queries evaluated at top-10 positions against authenticated non-empty gold sets ($|\text{Gold}_q| \ge 1$). | Contractual Target: Macro-Recall@10 = 100.0%, HitRate@10 = 100.0%. Empirical Status: 0/30 executed. | **Gated / Pending Authorization** |
| **AC-14** | Contamination Bound (Option A: $\le 5/150$) | `test_live_benchmark_contamination_option_a` | Live Pipeline | 30 queries evaluated at top-5 positions ($N_{\text{evaluated}}=150$). | Contractual Target: Contamination $\le 5/150 \approx 3.333\%$. Run halts if any query returns $< 5$ candidates. Empirical Status: 0/30 executed. | **Gated / Pending Authorization** |
| **AC-15** | Legacy regression suite preservation | Pytest 11 test modules | Pure Unit & Integration | 11 legacy test files executed in repository workspace with `$env:PYTHONPATH="."`. | **102 passed, 6 warnings in 34.28s (100.0%)**. Confirms 0 legacy regressions. | **TEST_EXECUTED (100% Passed)** |
| **AC-16** | Traceable candidate audit trail | `test_candidate_audit_trail_telemetry` | Pure Unit | Candidate list processed through `assemble_generation_context()`. | Audit report contains traceable inclusion/exclusion reason for every evaluated candidate. | **TEST_SPECIFIED** |
| **AC-17** | Article 212(1)(a) service-condition jurisdiction | `test_art212_service_conditions` | Pure Unit | (a) Civil servant challenging departmental promotion order (`2025 SCMR 134`); (b) Non-civil servant contractor. | In (a), Article 199 barred $\rightarrow$ Bucket 1B FST; in (b), returns `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`. | **TEST_SPECIFIED** |
| **AC-18** | Article 212(1)(b) public-service tort competence gate | `test_art212_tort_jurisdiction` | Pure Unit | (a) Tort claim against Government where enactment search shows no Art 212(1)(b) tribunal; (b) Suit filed with authentic S.80 notice; (c) Indian S.80(2) leave pleading. | In (a), returns `ARTICLE_212_TRIBUNAL_NOT_IDENTIFIED_ON_COMPLETED_ENACTMENT_SEARCH`; in (b), maintainable conditionally under S.9 CPC, indemnity, and S.80 notice; in (c), returns `REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2`. | **TEST_SPECIFIED** |
| **AC-19** | Article 212(1)(c) enemy-property jurisdiction | `test_art212_enemy_property` | Pure Unit | Dispute concerning enemy property custody under 1969 Ordinance. | Returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES; ENEMY_PROPERTY_CUSTODIAN_EXECUTIVE_JURISDICTION; JUDICIAL_REVIEW_MAINTAINABLE`. | **TEST_SPECIFIED** |
| **AC-20** | Article 212(2) provincial extension proviso | `test_art212_provincial_proviso` | Pure Unit | Provincial service tribunal candidate where parliamentary extension Act is enacted vs absent. | Art 212(2) bar applies only where extension Act enacted; otherwise evaluated under provincial law. | **TEST_SPECIFIED** |
| **AC-21** | Residuary Article 120 inheritance limitation & accrual | `test_inheritance_art120_denial` | Pure Unit | (a) Instrument cancellation pleaded; (b) Underspecified relief; (c) Clear declaration with unequivocal denial on Date $D$. | In (a), Art 91 evaluated; in (b), `LIMITATION_ARTICLE_UNRESOLVED`; in (c), residuary Art 120 applied strictly from Date $D$. | **TEST_SPECIFIED** |
| **AC-22** | Article 142 dispossession & ouster vs mutation | `test_inheritance_art142_dispossession` | Pure Unit | (a) Female co-heir never in sole possession challenging mutation; (b) Co-heir in possession subjected to ouster. | In (a), Art 142 rejected (no dispossession); In (b), Art 142 applied from date of actual ouster. | **TEST_SPECIFIED** |
| **AC-23** | Section 18 statutory fraud requirements | `test_inheritance_section18_fraud` | Pure Unit | Knowledge kept away by fraud or document fraudulently concealed vs bare non-communication of mutation. | Time runs from discovery upon proof of statutory fraud/concealment; bare non-communication fails. | **TEST_SPECIFIED** |
| **AC-24** | Authentic Section 2(8) Benami classification tree | `test_benami_sections_and_fiduciary` | Controlled Integration | (a) Fiduciary under 2(8)(A)(b)(i) with 5-predicate satisfaction (trustee, executor, director, agent, legal adviser); (b) Spouse/child/sibling/lineal with joint title + known resources under 2(8)(A)(b)(ii); (c) Brother A funds in sole name of Brother B; (d) Commercial agent holding on personal account; (e) Section 24 formal order. | (a) & (b) `BENAMI_EXCEPTION_ESTABLISHED`; (c) & (d) `POTENTIAL_BENAMI_TRANSACTION`; (e) `BENAMI_TRANSACTION_ADJUDICATED`. | **TEST_SPECIFIED** |
| **AC-25** | Section 489-F mens rea at cheque issuance & forum selection | `test_s489f_cumulative_ingredients` | Pure Unit | (a) Existing debt labeled "security"; (b) Pure advance contingent guarantee; (c) Liquidity failure evidence; (d) Private commercial recovery. | In (a), S.489-F admitted; in (b), S.489-F rejected; in (c), weighed as evidence; in (d), routed to Civil Court S.9/Order XXXVII CPC. | **TEST_SPECIFIED** |
| **AC-26** | Section 420 inception-intention test | `test_s420_inception_intention` | Pure Unit | Commercial contract breach without fraudulent inducement at inception (`1999 SCMR 1214`). | FIR quashment admitted to Bucket 1B; criminal cheating rejected. | **TEST_SPECIFIED** |
| **AC-27** | Section 406 entrustment versus debtor-creditor | `test_s406_debtor_creditor_entrustment` | Pure Unit | Purchase of goods on credit with default in repayment (`PLD 2004 SC 460`). | Criminal breach of trust rejected; debtor-creditor relationship verified. | **TEST_SPECIFIED** |
| **AC-28** | Amended Art 189 FCC/SC precedent binding ratio | `test_amended_art189_precedent_binding` | Pure Unit | (a) FCC ruling on legal ratio vs SC ruling; (b) FCC ruling lacking nexus; (c) Direct conflict with historical SC ruling; (d) Conflicting co-equal SC benches; (e) Conflicting co-equal FCC benches. | In (a), FCC ratio binds SC; in (b), SC controls only if on point; in (c), returns `PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT`; in (d), `UNRESOLVED_CO_EQUAL_APEX_CONFLICT`; in (e), `UNRESOLVED_CO_EQUAL_FCC_CONFLICT`. | **TEST_SPECIFIED** |
| **AC-29** | Deployed request recount & non-ASCII boundaries | `test_native_tokenizer_full_payload_boundary` | Controlled Integration | Serialized request with message framing, Urdu legal text, XML tags; native tokenizer execution; recount. | Context window ceiling $\le 7,000$ strictly enforced; concatenation boundary verified; non-ASCII handled. | **TEST_SPECIFIED** |
| **AC-30** | Benchmark dual-denominator & ground-truth protocol | `test_benchmark_reproducibility_denominator` | Live Pipeline | 30 queries evaluated across: (a) top-10 positions ($N_{\text{queries}}=30$); (b) top-5 positions (Option A: $N_{\text{evaluated}}=150$). Baseline artifacts verified by commit `7378557` and recorded SHA-256 hashes. | Evaluates Macro-Recall@10 = 100%, HitRate@10 = 100%, and Contamination $\le 5/150$ with independent reporting. Empirical Status: 0/30 executed. | **Gated / Pending Authorization** |

---

## 7. Standing Invariants & Pre-Authorization Sign-Off Gate

The execution remains completely stopped under these strict invariants:
1. **Zero Production Code Edits:** `main.py` and `legal_ai/retrieval/unified_orchestrator.py` remain untouched.
2. **Zero Premature Implementation:** `core/post_rerank_domain_gate.py` has not been authored.
3. **Zero Vector Index Modifications:** Pinecone database (401,351 vectors) remains unmodified.
4. **Zero Supabase Schema Migrations:** Database schema and indexes remain unmodified.
5. **Phase 4, Step 5 Implementation Status:** **PAUSED — Awaiting Explicit User Authorization.**
6. **Phase 4, Step 6 Status:** **STRICTLY BLOCKED / UNAUTHORIZED.**
