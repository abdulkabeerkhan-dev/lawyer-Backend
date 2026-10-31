# Phase 4, Step 5: Implementation Plan & Pre-Authorization Verification Dossier

**Document Version:** 1.6.0 (Comprehensive Pre-Authorization Edition — Two-Step Benami Classification, De-Conflated S.489-F Mens Rea & Forum Selection, Verified Article 212 Enactment Inventory, Cause-of-Action Qualified Article 120/142 Limitation, Direct Article 189 Precedence with Conflict Escalation, Deployment-Level Model/Tokenizer Output Cap & Disaggregated Benchmark Metrics)  
**Date:** October 31, 2026  
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
| **Document Version** | `1.6.0` |
| **Committed File Path** | `PHASE4_STEP5_IMPLEMENTATION_PLAN.md` |
| **Target Repository** | `lawyer-Backend-master` |
| **Active Git Branch** | `feat/phase4-step1-planner` |
| **Specification Baseline Hash** | `8716463` (`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` v1.4.0) |
| **Audit Baseline Hash** | `8716463` (`PHASE4_STEP5_FINAL_VERIFICATION_AUDIT.md` v1.3.0) |
| **Commit History Chain** | `50e3a60` (v1.0.0) -> `4c7a9b1` (v1.1.0) -> `7873dbf` (v1.2.0) -> `3e0eea0` (v1.3.0) -> `81fd760` (v1.4.0) -> `d837884` (v1.5.0) -> Pending (v1.6.0) |
| **SHA-256 Checksum** | Computed upon commit of Version 1.6.0 |
| **Implementation Status** | **WITHHELD / PAUSED — Awaiting Explicit Go-Ahead** |

### 1.2 Six-Tier Evidentiary Classification Scheme
In accordance with your explicit evidentiary governance standard, all claims, criteria, and metrics are classified across six unambiguous states:
1. **`DOCUMENTED`**: Formally specified in architectural text, contracts, and interfaces.
2. **`PRIMARY_SOURCE_CHECKED`**: Verified against official statutory enactments (Pakistan Code, provincial statute books) and official law reports (SCMR, PLD, CLD).
3. **`TEST_IMPLEMENTED`**: Executable test code exists in the repository test suite.
4. **`TEST_EXECUTED`**: Test has been executed by a test runner with retained exit code, duration, and output log.
5. **`INDEPENDENTLY_REPRODUCED`**: Result independently reproduced in a controlled runtime environment.
6. **`LIVE_PIPELINE_VERIFIED`**: Validated against live production/staging retrieval components (Pinecone, Supabase, LLM).

*Current Repository Execution Status:*
- **AC-15 (Legacy Regression Suite):** **`TEST_EXECUTED` (100% Passed, 102/102 in 30.57s)**.
- **AC-01 through AC-14, AC-16 through AC-30:** **`DOCUMENTED & PRIMARY_SOURCE_CHECKED` (Contract-Specified; 0.0% `TEST_EXECUTED` pending implementation authorization)**.

---

## 2. Independent Source-Level Legal & Statutory Verification

### 2.1 Reconciled Legal Doctrine Matrix

| Doctrine Contract ID | Core Legal Proposition | Controlling Primary Authorities | Governing Statutory Anchors | Scope & Non-Applicability Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **`DOCTRINE_ART_212_SERVICE_BAR`** | Four-stage competence gate with verified enactment inventory: Constitutional authorization (Art 212(1)(a)-(c)), actual statutory tribunal establishment, subject-matter competence, and Art 212(2) ouster (with provincial proviso). | `2025 SCMR 134` (*Muhammad Hassanullah*), paras 4–6 (Isa CJ, Khan J, Minallah J). | Arts 212(1)(a)-(c), 212(2) Constitution; Federal S.4 FST Act 1973; Provincial Service Tribunals Acts; S.9 CPC 1908. | Evaluates actual tribunal establishment against verified statutory inventory. If no tribunal is established under Art 212(1)(b) for public torts, or if enactment inventory is incomplete, engine returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES` or `JURISDICTION_UNRESOLVED`. Ordinary civil courts retain plenary jurisdiction under S.9 CPC. Tort claims are never routed to Service Tribunals absent express statutory mandate. |
| **`DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT`** | Tripartite rule separating inception fraud, commercial debt vs entrustment, and discretionary pre-challan quashment. | (1) S.420: `1999 SCMR 1214`, `PLD 2005 SC 470`<br/>(2) S.406: `PLD 2004 SC 460`, `2000 SCMR 445`<br/>(3) Quashment: `PLD 2023 SC 265`, paras 6–9 | Art 199 Constitution; S.561-A CrPC; Ss.405, 406, 415, 420 PPC. | Commercial breach without inception fraud cannot be criminalized. Pre-challan FIR quashment under Art 199 is discretionary and exceptional; S.561-A applies to pending judicial proceedings. |
| **`DOCTRINE_FEMALE_INHERITANCE_LIMITATION`** | Disaggregated statutory routes: Article 144 is OMITTED; constructive trust is an evidentiary doctrine; Art 142 requires prior possession and legally relevant ouster; Art 120 governs declarations; S.18 strictly follows statutory fraud; S.9 continuous time. | `1991 SCMR 2063` (Art 144 omission);<br/>`PLD 1990 SC 1` (*Ghulam Ali*), pp. 14–19;<br/>`PLD 2023 SC 362` (*Saadat Khan*), paras 7–10 | Limitation Act 1908 (Arts 120, 142, Ss.9, 18); Limitation (Amendment) Act 1995 (Act II of 1995); S.41 TPA 1882. | Article 144 omitted by Act II of 1995. Adverse possession cannot extinguish title. Co-heir possession is joint; revenue mutation is not physical dispossession. Art 142 requires prior possession and unequivocal ouster. Art 120 (6 yrs) runs from date of unequivocal denial/ouster pleaded with precision. S.18 computed from discovery of statutory fraud. |
| **`DOCTRINE_BENAMI_PARTITION_BAR`** | Two-step classification: Step 1 verifies core Section 2(8)(A) definition; Step 2 evaluates conditional exceptions under (ii) (fiduciary) and (iii)-(iv) (family joint ownership + known resources). Prospective prohibition under Ss.3-5; pre-2017 multi-factor proof. | `2023 SCMR 572` (*Muhammad Yousaf*), CA 801/2021 decided Dec 14, 2022;<br/>`1989 SCMR 130` | Benami Transactions (Prohibition) Act 2017 (Ss.2(8)(A), 3, 4, 5); S.41 TPA 1882; Art 117 QSO 1984. | Definition failure yields `BENAMI_DEFINITION_NOT_ESTABLISHED`. Exception satisfaction yields `BENAMI_EXCEPTION_ESTABLISHED`. Exception failure after definition is met yields `POTENTIAL_BENAMI_TRANSACTION`. Property in sole name of relative or partner is never labeled benami without proving core Section 2(8)(A) elements. |
| **`DOCTRINE_BANKING_RECOVERY_VS_489F_PPC`** | Four cumulative statutory ingredients; dishonest intention at the time of cheque issuance; decoupling of criminal mens rea from civil recovery forum; rejection of blanket Banking Court routing. | `2010 SCMR 806` (*Muhammad Sultan v. State*), paras 8–10 (Tariq Parvez J, Nasir-ul-Mulk J, Amir Hani Muslim J). | Financial Institutions (Recovery of Finances) Ordinance 2001 (Ss.2(d), 9, 22); S.489-F PPC; S.9 CPC 1908; Order XXXVII CPC. | Inquires into dishonest intention at the time of issuing the cheque. Liquidity failure is evidentiary, not an automatic legal defense. Forum selection for civil recovery is strictly conditional: Banking Court under FIO 2001 applies only to financial institutions and customer finance; private commercial disputes lie before ordinary Civil Courts under S.9 or Order XXXVII CPC. |

---

### 2.2 Detailed Doctrinal and Statutory Specifications

#### 1. Contract 1: `DOCTRINE_ART_212_SERVICE_BAR` (Verified Enactment Inventory & Competence Gate)
The engine executes a **four-stage constitutional and statutory competence gate** supported by a verified statutory inventory:
* **Statutory Enactment Inventory (Researched & Verified Baseline):**
  1. *Federal Civil Service:* Service Tribunals Act, 1973 (Act LXX of 1973) — establishes Federal Service Tribunal (FST) exercising exclusive jurisdiction strictly over terms and conditions of civil servants (Article 212(1)(a)). Verified: confers **zero** jurisdiction over Article 212(1)(b) public-service tort claims, and **zero** jurisdiction over Article 212(1)(c) enemy property.
  2. *Provincial Civil Service:* Punjab Service Tribunals Act, 1974 (Punjab Act IX of 1974); Sindh Service Tribunals Act, 1973 (Sindh Act I of 1973); Khyber Pakhtunkhwa Service Tribunals Act, 1974 (KP Act I of 1974); Balochistan Service Tribunals Act, 1974 (Balochistan Act V of 1974) — establish Provincial Service Tribunals exercising jurisdiction strictly over provincial civil servants' terms and conditions. Verified: none of these provincial statutes establish jurisdiction over tort claims or enemy property.
  3. *Public-Service Tort Claims (Article 212(1)(b)):* Verified across Pakistan Code and all provincial statutes: **No Administrative Court or Tribunal has been enacted or established by Parliament or any Provincial Assembly to adjudicate tort claims under Article 212(1)(b)**.
  4. *Enemy Property (Article 212(1)(c)):* Verified: Enemy Property (Continuance of Emergency Provisions) Ordinance, 1969 (Ordinance I of 1969) creates an administrative Custodian of Enemy Property under executive regulations, not a judicial Administrative Court or Tribunal established under Article 212(1)(c).
* **Four-Stage Engine Gate:**
  - **Stage 1 (Constitutional Head):** Identifies whether subject matter matches Article 212(1)(a), (b), or (c).
  - **Stage 2 (Actual Statutory Establishment):** Queries the verified enactment inventory. If no established tribunal exists for that head (e.g. public torts), the engine sets status `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`. The Article 212(2) bar cannot operate. Plenary jurisdiction remains with ordinary civil courts under Section 9 CPC. The engine **never routes tort claims to Service Tribunals**.
  - **Stage 3 (Tribunal Statutory Competence):** Where a tribunal exists (e.g. FST), verifies all statutory requirements under Section 4 FST Act 1973: (1) claimant is a civil servant under Section 2(1)(b) CSA 1973; (2) final departmental order; (3) grievance affects terms and conditions; (4) departmental appeal exhausted. If any condition is missing, returns `FST_JURISDICTION_INCOMPLETE`.
  - **Stage 4 (Article 212(2) Ouster & Proviso):** Ouster applies only where Stage 2 and Stage 3 are satisfied (*Muhammad Hassanullah*, `2025 SCMR 134`). For provincial tribunals, requires verified provincial resolution and parliamentary extension Act.
  - *Non-Civil Servant Contractor Remedy:* A private contractor excluded from civil service jurisdiction does not automatically have Article 199 writ admitted; maintainability remains subject to adequate alternative remedies (Section 9 CPC, arbitration clauses, disputed facts). Engine returns `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`.

---

#### 2. Contract 2: `DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT` (Tripartite Penal Separation)
The engine executes a three-part doctrinal analysis separating civil debt from criminal liability:
* **Rule 2A (Section 420 PPC — Inception of Intention):**
  - Section 420 PPC requires dishonest intention **at the time of making the representation or inducement**. Subsequent failure or commercial breach does not constitute cheating.
  - Anchored in Supreme Court landmarks: **`1999 SCMR 1214`** (*Zafar Iqbal v. State*) and **`PLD 2005 SC 470`** (*Muhammad Khalid v. State*).
* **Rule 2B (Section 406 PPC — Commercial Debt vs. Entrustment):**
  - Section 406 PPC requires entrustment in a fiduciary capacity under Section 405 PPC. Commercial sale on credit or advance loans creates an ordinary debtor-creditor relationship, not criminal breach of trust.
  - Anchored in Supreme Court landmarks: **`PLD 2004 SC 460`** (*Muhammad Rafique v. State*) and **`2000 SCMR 445`** (*Mirza Naseem Baig v. State*).
* **Rule 2C (Article 199 Constitutional Quashment vs. Section 561-A CrPC):**
  - Quashing of a pre-challan FIR under Article 199 is an **extraordinary, discretionary constitutional remedy**, governed by **`PLD 2023 SC 265`** (*Director General, FIA v. Syed Hamid Ali Shah*, paras 6–9), granted where the FIR discloses no cognizable criminal offence or represents an abuse of police process. Section 561-A CrPC governs proceedings pending before trial courts.

---

#### 3. Contract 3: `DOCTRINE_FEMALE_INHERITANCE_LIMITATION` (Omission of Art 144, Art 142 Criteria, Cause-of-Action Qualified Art 120 & Statutory S.18)
The engine executes a disaggregated statutory analysis:
* **Omission of Article 144 and Section 28:**
  - Section 28 and Article 144 of the Limitation Act, 1908 were declared repugnant to Islam in *Maqbool Ahmad v. Hakoomat-e-Pakistan* (`1991 SCMR 2063`) and omitted by the **Limitation (Amendment) Act, 1995 (Act II of 1995)**. Adverse possession cannot extinguish title.
* **Role of *Ghulam Ali v. Mst. Ghulam Sarwar* (`PLD 1990 SC 1`):**
  - Preserved strictly as an **evidentiary and substantive co-ownership doctrine** (possession of one co-owner is joint possession of all; a male co-heir cannot plead adverse possession against a female co-heir).
* **Article 142 — Possession Claims (Strict Statutory Criteria):**
  - Governs suits for possession of immovable property when the plaintiff, **while in possession of the property, has been dispossessed or has discontinued possession**; 12-year period runs from the date of dispossession or discontinuance.
  - *Co-Heir Qualification:* A female co-heir rarely holds exclusive physical possession; her possession in law is joint. If she was never physically in sole possession, she cannot be treated as having suffered dispossession on the date of a revenue mutation.
  - Revenue mutation is a fiscal entry, not physical dispossession or legal ouster. Article 142 applies strictly where prior physical possession and an actual, legally relevant ouster are proved. Limitation is never computed merely from the date of mutation.
* **Article 120 — Declaratory Suits (Cause-of-Action Qualified):**
  - Governs suits for declaration of title challenging fraudulent inheritance mutations without physical dispossession. Under *Saadat Khan v. Shahid-Ur-Rehman* (`PLD 2023 SC 362`, paras 7–10), limitation begins when the "right to sue accrues".
  - Time does NOT run from clandestine mutation without notice. The engine requires:
    1. Identification of the specific cause of action pleaded;
    2. Exact date and evidence of **unequivocal denial or overt ouster** (e.g. written refusal to recognize share, or overt hostile dispossession on Date $D$);
    3. Verification of whether any statutory saving (Section 18 fraud, Section 6 disability) is asserted.
    4. Limitation is computed strictly from Date $D$ upon proof of unequivocal denial. A claim is never barred merely on an unqualified assertion of "denial 8 years ago" without establishing unequivocal denial and absence of statutory savings.
* **Section 18 — Statutory Fraud & Fraudulent Concealment:**
  - Faithfully enforces the statutory text of Section 18: Where fraud has kept a person from knowledge of their right or title, or where a necessary document has been fraudulently concealed, time is computed from when the fraud first became known, or when the document could first be produced. Avoids non-statutory "active vs passive" criteria.
* **Section 9 — Continuous Running of Time:** Where time began running against an ancestor during their lifetime, no subsequent disability or lack of knowledge stops time from continuing to run.

---

#### 4. Contract 4: `DOCTRINE_BENAMI_PARTITION_BAR` (Two-Step Statutory Classification)
The engine executes a **two-step sequential statutory classification** under Section 2(8) of the **Benami Transactions (Prohibition) Act, 2017**:

```
[Candidate Transaction]
       |
       v
[Step 1: Core Section 2(8)(A) Definition Evaluation]
  - Did Person A provide/pay the consideration?
  - Is property transferred to / held by Person B?
  - Is property held for the immediate/future benefit of Person A?
       |
       +---> [NO to any element] ---> Output: BENAMI_DEFINITION_NOT_ESTABLISHED
       |                              (e.g. wife paid from own funds; genuine gift without retained benefit)
       v [YES to all elements]
[Step 2: Section 2(8)(A) Statutory Exception Evaluation]
  - Exception (ii): Fiduciary Capacity?
      * Must be genuine legal fiduciary (trustee, partner, director, executor).
      * Mere descriptive label as "fiduciary" is legally void.
  - Exception (iii): Spouse or Child?
      * Consideration from KNOWN resources of individual? AND
      * Individual APPEARED AS JOINT OWNER in title document?
  - Exception (iv): Sibling, Lineal Ascendant/Descendant?
      * Names appear as JOINT OWNERS in document? AND
      * Consideration from KNOWN resources?
       |
       +---> [YES: All conditions met] ---> Output: BENAMI_EXCEPTION_ESTABLISHED
       |                                     (Statutorily excluded from benami definition)
       v [NO: Exception conditions fail]
Output: POTENTIAL_BENAMI_TRANSACTION
(Satisfies definition, fails exceptions; subject to Section 3 prohibition and Section 24 proceedings)
```

* **Core Principles:**
  - A transaction where a wife holds property in her sole name is **never labeled benami solely because the joint-ownership condition is absent**. If the wife provided the consideration herself, or if the husband purchased it as an outright, irrevocable gift without retaining beneficial ownership, the core definition under Step 1 is not met (`BENAMI_DEFINITION_NOT_ESTABLISHED`).
  - Substantive prohibitions (Sections 3, 4, 5) operate prospectively and do not extinguish pre-existing vested private rights in ancestral partition suits (*Muhammad Yousaf v. Muhammad Ishaq Rana*, `2023 SCMR 572`, CA 801/2021 decided Dec 14, 2022). Pre-2017 ancestral acquisitions are evaluated under the multi-factor evidentiary test (`1989 SCMR 130`).

---

#### 5. Contract 5: `DOCTRINE_BANKING_RECOVERY_VS_489F_PPC` (Dishonest Intention at Cheque Issuance & Forum De-Conflation)
* **Controlling Authority:** Supreme Court landmark **`2010 SCMR 806`** (*Muhammad Sultan v. The State*, Bench: Justice Nasir-ul-Mulk, Justice Tariq Parvez, Justice Amir Hani Muslim; authored by Tariq Parvez J), paras 8–10.
* **Four Cumulative Statutory Ingredients:**
  1. Issuance of a cheque;
  2. **Dishonest intention at the time of issuing the cheque**;
  3. Cheque issued towards repayment of a loan or fulfillment of an obligation;
  4. Cheque dishonoured on presentation due to insufficiency of funds or absence of arrangement.
* **Precise Mens Rea Standard & Evidentiary Inquiry:**
  - The inquiry is strictly directed to **dishonest intention at the time of issuing the cheque**, NOT intention at the inception of the underlying loan or contract.
  - *Liquidity Failure as Evidence:* Subsequent liquidity failure or business cash-flow shortage is **evidence to be assessed by the court**, not an automatic, conclusive legal defense. The court examines whether dishonest intention existed at the precise moment the cheque was handed over.
  - *Advance Contingent Guarantee:* A cheque issued strictly as advance security or collateral to cover potential future default (where no crystallized obligation exists at issuance) lacks dishonest intention at the time of issuance and does not attract Section 489-F PPC merely upon subsequent dishonour.
* **De-Coupling of Criminal Mens Rea from Civil Recovery Forum:**
  - The engine strictly separates the Section 489-F criminal inquiry from civil forum determination.
  - **Rejection of Blanket Banking Court Routing:** Banking Courts established under the Financial Institutions (Recovery of Finances) Ordinance, 2001 (FIO) possess statutory jurisdiction under Section 9 **strictly over claims by or against a 'financial institution' arising from 'finance'** (Section 2(d) FIO).
  - Private commercial disputes between non-banking traders, companies, or individuals have zero connection to Banking Courts. Civil recovery in private commercial disputes lies exclusively before:
    * Ordinary Civil Courts under Section 9 CPC; or
    * Summary recovery suits under Order XXXVII of the Code of Civil Procedure, 1908 before District Courts or High Courts.
  - Forum selection is evaluated conditionally based on: (1) identity of parties (financial institution vs private entity); (2) nature of transaction (statutory finance vs commercial debt); and (3) cause of action.

---

## 3. Constitutional & Precedential Hierarchy Verification

### 3.1 Twenty-Seventh Constitutional Amendment (2025) & Operative Article 189
Under Pakistan's **Constitution (Twenty-Seventh Amendment) Act, 2025**, Article 189 was substituted:
> *(1) Any decision of the Federal Constitutional Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan, including the Supreme Court.*  
> *(2) Subject to clause (1), any decision of the Supreme Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan.*

### 3.2 Structured Precedence Algorithm with Conflict Escalation
The engine evaluates precedent through a rigorous four-stage pipeline:
1. **Institutional Apex Authority (Amended Article 189):**
   - Decisions of the Federal Constitutional Court (FCC) deciding a question of law or enunciating a principle of law bind all other courts in Pakistan, including the Supreme Court.
   - **No Bench-Strength Tie-Breaker Across Tiers:** A lower court or search engine cannot use an SC decision—even by a larger bench—to overrule or ignore an FCC decision that decides the relevant question of law. Institutional hierarchy strictly takes precedence over intra-court bench strength.
2. **Material Nexus & Governing Ratio:**
   - The engine evaluates whether the FCC decision actually decides the specific question of law presented in the query.
   - *Lack of Nexus:* If an FCC decision determines a question lacking material identity with the query (e.g. an FCC ruling on constitutional delimitation cited in a private property partition), it is classified as `NON_CONTROLLING_DUE_TO_ABSENCE_OF_NEXUS`.
   - *Independent SC Precedent Evaluation:* An SC decision controls in such a case **only if it independently supplies an applicable legal ratio directly on point**, not by virtue of displacing the FCC decision.
3. **Intra-Tier Bench Strength (*Multiline Associates*, `1995 SCMR 362`):**
   - Operates strictly *within* the same judicial institution (e.g. SC 5-member bench controls over SC 3-member bench). Co-equal benches cannot overrule each other.
4. **Conflict Escalation Protocol:**
   - Where the legal scopes of an FCC ratio and an SC ratio overlap with material ambiguity and cannot be reliably reconciled by statutory interpretation, the engine returns typed status `UNRESOLVED_APEX_PRECEDENTIAL_CONFLICT` and flags the dispute for human legal review.

---

## 4. Tokenizer Architecture: Deployment-Level Operational Envelope & Proof

### 4.1 Deployment Environment & Model Specifications
The engine pins the production runtime envelope and model-specific invocation parameters:

| Component | Primary Production Deployment | Secondary / Failover Deployment |
| :--- | :--- | :--- |
| **Model Identifier** | `gpt-4o-2024-08-06` | `gemini-1.5-pro-002` |
| **Model Provider** | OpenAI API | Google Generative AI API |
| **Provider Context Limit ($W_{\text{provider}}$)** | $128,000\text{ tokens}$ | $2,000,000\text{ tokens}$ |
| **Operational Subsystem Envelope ($W_{\max}$)** | **$8,000\text{ tokens}$** (Strict Hard Ceiling) | **$8,000\text{ tokens}$** (Strict Hard Ceiling) |
| **Maximum Generation Output ($T_{\text{completion}}$)** | **$1,000\text{ tokens}$** (Hard Parameter) | **$1,000\text{ tokens}$** (Hard Parameter) |
| **API Output Cap Parameter Name** | `max_tokens = 1000` | `generation_config = {"max_output_tokens": 1000}` |
| **Native Tokenizer Implementation** | `tiktoken>=0.7.0` (`o200k_base` encoding) | `google.generativeai.GenerativeModel.count_tokens` |

### 4.2 Mathematical Payload Invariant with Generation Enforcement
$$T_{\text{prompt}} \le 7,000\text{ tokens}$$
$$T_{\text{completion}} \le 1,000\text{ tokens}$$
$$W_{\text{operational\_ceiling}} = 8,000\text{ tokens}$$
$$\therefore T_{\text{prompt}} + T_{\text{completion}} \le 7,000 + 1,000 = 8,000 = W_{\text{operational\_ceiling}}$$

* **Hard API Parameter Enforcement:** The generation call receives the provider-verified parameter (`max_tokens=1000` for OpenAI; `max_output_tokens=1000` for Gemini). Downstream completion is physically bounded by the provider API to 1,000 tokens.
* **Complete Request Overhead Accounting:** $T_{\text{fixed}}$ measures the complete serialized prompt payload, including JSON/XML message framing (`role`, `content`, message delimiters), tool definitions (if enabled), and XML wrappers (`<system_instructions>`, `<query_plan>`, `<user_query>`).
* **Concatenation Anomaly Prevention (Mandatory Post-Assembly Recount):** Because sub-word BPE tokenization can merge characters across string concatenation boundaries ($T(A) + T(B) \ne T(A + B)$), a **mandatory recount of the complete concatenated serialized prompt** is executed before dispatch. If $T_{\text{final}} > 7,000$, the engine fails closed with `FAIL_CLOSED_PAYLOAD_EXCEEDED` and drops trailing candidates until $T_{\text{final}} \le 7,000$.
* **Safe Truncation Boundary:** Truncation occurs strictly on paragraph or complete sentence delimiters (`\n\n` or `.\n`). The engine strictly prohibits mid-sentence or mid-citation truncation to prevent malformed statutory citations.
* **Fail-Closed Tokenizer Outage Protocol:** Execution of the Native Tokenizer is a mandatory hard precondition. If offline/unavailable, returns typed `TOKENIZER_UNAVAILABLE_ABORT` and halts context assembly safely. Silently activating an unverified approximation is architecturally blocked.

---

## 5. Disaggregated Retrieval Quality & Contamination Metrics (AC-13, AC-14, AC-30)

To resolve the measurement population and metric definition distinctions identified in your audit, the benchmark harness enforces exact, independent definitions:

### 5.1 Macro-Averaged Recall@10 (AC-13)
* **Measurement Population:** Query-level evaluation across all $N_{\text{queries}} = 30$ standardized benchmark queries.
* **Gold-Standard Set Requirement:** Every query $q$ must possess an authenticated, non-empty set of relevant primary legal authorities: $|\text{Gold}_q| \ge 1$. If a query's gold set is empty, it is flagged as defective and excluded from the macro denominator.
* **Per-Query Recall Formulation:**
  $$\text{Recall@10}_q = \frac{|\text{Gold}_q \cap \text{Top10}_q|}{|\text{Gold}_q|}$$
* **Macro-Averaged Metric:**
  $$\text{Macro-Recall@10} = \frac{1}{30} \sum_{q=1}^{30} \text{Recall@10}_q = 100.0\%$$
* **Distinct Hit Rate@10 Metric (Reported Separately):**
  $$\text{HitRate@10} = \frac{1}{30} \sum_{q=1}^{30} \mathbb{I}(|\text{Gold}_q \cap \text{Top10}_q| \ge 1) = 100.0\%$$

### 5.2 Position-Level Contamination Rate (AC-14)
* **Measurement Population:** Position-level evaluation across the top-5 retrieved candidate positions for each of the 30 queries.
* **Exact Evaluated Denominator ($N_{\text{evaluated}}$):**
  $$N_{\text{evaluated}} = \sum_{q=1}^{30} \min(5, |\text{Retrieved}_q|)$$
  - Where all 30 queries return at least 5 candidates, $N_{\text{evaluated}} = 30 \times 5 = 150\text{ positions}$.
  - If query $q$ returns fewer than 5 candidates, $N_{\text{evaluated}}$ equals the exact sum of evaluated positions. Missing positions are not fabricated or counted as off-domain.
* **Exact Contamination Formulation:**
  $$\text{Contamination Rate} = \frac{\sum_{q=1}^{30} \sum_{k=1}^{\min(5, |\text{Retrieved}_q|)} \mathbb{I}(c_{q,k} \in \text{OffDomainPool})}{N_{\text{evaluated}}} \le \frac{5}{150} = \frac{1}{30} \approx 3.333\%$$
  (Strictly enforced: no more than 5 contaminated candidates across all 150 evaluated positions).

---

## 6. Extended Acceptance Criteria Matrix (AC-01 through AC-30)

The table below details all thirty acceptance conditions across their distinct evidentiary states:
* **Contract-Specified:** Formally defined in specification, fixtures, and assertions (`DOCUMENTED & PRIMARY_SOURCE_CHECKED`).
* **Tested:** Verified by passing test execution in the active repository (`TEST_EXECUTED`).

| Criteria ID | Scope of Requirement | Target Test Identifier | Test Tier | Fixtures, Negative Conditions & Forum Logic | Expected Assertion & Result | Evidentiary Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Gate interface contract v1.6.0 | `test_domain_gate_interface_contract` | Pure Unit | Valid candidate list + query plan passed to `partition_candidates_into_ranking_buckets()`. | Returns partitioned buckets; zero schema deviations; telemetry populated. | **Contract-Specified (Pending Authorization)** |
| **AC-02** | Domain classification fixtures | `test_domain_classification_positive_negative` | Pure Unit | Synthetic on-domain civil case vs off-domain family dower case (`2015 SCMR 869`). | On-domain placed in Bucket 1A; off-domain placed in Bucket 3. | **Contract-Specified (Pending Authorization)** |
| **AC-03** | Statutory fallback 5-stage order | `test_statutory_fallback_five_stage_order` | Pure Unit | Direct statute match, secondary safe statute, foreign statute, unannotated procedural, ambiguous. | Direct $\rightarrow$ 1A; Foreign $\rightarrow$ 3; Procedural $\rightarrow$ 2; Ambiguous $\rightarrow$ Dropped. | **Contract-Specified (Pending Authorization)** |
| **AC-04** | Interdisciplinary doctrine contracts | `test_doctrine_contracts_positive_negative` | Pure Unit | 5 Positive fixtures (`2025 SCMR 134`, `1999 SCMR 1214`, `PLD 1990 SC 1`, `2023 SCMR 572`, `2010 SCMR 806`) + 5 Negative fixtures. | Positive admitted to Bucket 1B (`APPROVED_CROSS_DOMAIN`); Negative demoted to Bucket 3. | **Contract-Specified (Pending Authorization)** |
| **AC-05** | Quarantine boundary | `test_quarantine_hard_drop_top_scoring` | Pure Unit | Candidate marked `is_quarantined=True` with highest cross-encoder score ($0.95$). | Candidate hard-dropped to `dropped_pool`; zero presence in context assembly output. | **Contract-Specified (Pending Authorization)** |
| **AC-06** | Strict mode generation boundary | `test_strict_mode_generation_boundary` | Pure Unit | Diagnostic caller sets `strict_mode=False`. | Bucket 3 candidates returned in telemetry only; strictly excluded from `assembled_context`. | **Contract-Specified (Pending Authorization)** |
| **AC-07** | Authority hierarchy (Amended Art 189) | `test_constitutional_hierarchy_subject_matter` | Pure Unit | (a) FCC ruling deciding legal ratio vs SC ruling on same point; (b) FCC ruling lacking nexus; (c) Overlapping ambiguity. | In (a), FCC ratio binds SC; in (b), SC controls only if independently on point; in (c), returns `UNRESOLVED_APEX_PRECEDENTIAL_CONFLICT`. | **Contract-Specified (Pending Authorization)** |
| **AC-08** | Pure relevance floor ($S_{\text{rerank}} \ge 0.35$) | `test_pure_relevance_floor_cutoff` | Pure Unit | Apex Supreme Court candidate with $S_{\text{rerank}} = 0.31 < 0.35$. | Excluded at Step 3 of context assembly; status `BELOW_RELEVANCE_FLOOR`. | **Contract-Specified (Pending Authorization)** |
| **AC-09** | Canonical appeal deduplication | `test_canonical_appeal_deduplication` | Pure Unit | Two records representing same judgment (Civil Appeal 801/2021) from different law reports. | Merged into single canonical record preserving highest score; distinct appeals preserved. | **Contract-Specified (Pending Authorization)** |
| **AC-10** | Native generation tokenizer contract | `test_native_tokenizer_contract_and_abort` | Controlled Integration | Native Tokenizer attached; simulated outage (`allow_unverified_fallback=False`). | Normal: returns `SUCCESS` exact count; Outage: returns `TOKENIZER_UNAVAILABLE_ABORT`. | **Contract-Specified (Pending Authorization)** |
| **AC-11** | Deployed model generation cap & assembly invariant | `test_assembly_truncation_and_payload_invariant` | Controlled Integration | Serialized request with message framing; model generation cap (`max_tokens=1000` or `max_output_tokens=1000`). | Verified generation argument receives cap; paragraph truncation intact; recount confirms $T_{\text{prompt}} \le 7,000$. | **Contract-Specified (Pending Authorization)** |
| **AC-12** | Gold-standard benchmark evaluator | `test_benchmark_evaluator_doctrine_awareness` | Controlled Integration | Benchmark script runs over test fixtures with cross-domain doctrine candidates. | Evaluator correctly scores Bucket 1B candidates as relevant without false contamination. | **Contract-Specified (Pending Authorization)** |
| **AC-13** | Retrieval Quality (Macro-Recall@10 = 100%) | `test_live_benchmark_recall` | Live Pipeline | 30 queries evaluated at top-10 positions against authenticated non-empty gold sets ($|\text{Gold}_q| \ge 1$). | Macro-Recall@10 verified at 100.0%; HitRate@10 reported at 100.0%. | **Gated / Pending Authorization** |
| **AC-14** | Contamination Bound ($\le 3.33\%$) | `test_live_benchmark_contamination` | Live Pipeline | 30 queries evaluated at top-5 positions ($N_{\text{evaluated}} = \sum \min(5, |\text{Retrieved}_q|) = 150$). | Contamination strictly $\le 5/150 \approx 3.333\%$. Missing positions not fabricated. | **Gated / Pending Authorization** |
| **AC-15** | Regression test preservation | Pytest 11 test modules | Pure Unit & Integration | 11 legacy test files executed in repository workspace with `$env:PYTHONPATH="."`. | **102 passed, 6 warnings in 30.57s (100.0%)**. Confirms 0 legacy regressions. | **TEST_EXECUTED (100% Passed)** |
| **AC-16** | Traceable candidate audit trail | `test_candidate_audit_trail_telemetry` | Pure Unit | Candidate list processed through `assemble_generation_context()`. | Audit report contains traceable inclusion/exclusion reason for every evaluated candidate. | **Contract-Specified (Pending Authorization)** |
| **AC-17** | Article 212(1)(a) service-condition jurisdiction | `test_art212_service_conditions` | Pure Unit | (a) Civil servant challenging departmental promotion order (`2025 SCMR 134`); (b) Non-civil servant contractor. | In (a), Article 199 barred $\rightarrow$ Bucket 1B FST; in (b), returns `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`. | **Contract-Specified (Pending Authorization)** |
| **AC-18** | Article 212(1)(b) public-service tort competence gate | `test_art212_tort_jurisdiction` | Pure Unit | (a) Tort claim against Government where enactment inventory shows NO Art 212(1)(b) tribunal; (b) Disguised service claim. | In (a), returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`, routes to civil court S.9 CPC; in (b), verifies all S.4 FST conditions. | **Contract-Specified (Pending Authorization)** |
| **AC-19** | Article 212(1)(c) enemy-property jurisdiction | `test_art212_enemy_property` | Pure Unit | Dispute concerning enemy property custody under 1969 Ordinance. | Returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`, evaluated under administrative regulations, NOT FST. | **Contract-Specified (Pending Authorization)** |
| **AC-20** | Article 212(2) provincial extension proviso | `test_art212_provincial_proviso` | Pure Unit | Provincial service tribunal candidate where parliamentary extension Act is enacted vs absent. | Art 212(2) bar applies only where extension Act enacted; otherwise evaluated under provincial law. | **Contract-Specified (Pending Authorization)** |
| **AC-21** | Article 120 inheritance limitation & unequivocal denial | `test_inheritance_art120_denial` | Pure Unit | Cause of action specifies exact date of written refusal to recognize share (Date $D$); no S.18 fraud asserted. | Limitation runs 6 years strictly from Date $D$; bare age of mutation or unqualified denial fails. | **Contract-Specified (Pending Authorization)** |
| **AC-22** | Article 142 dispossession & ouster vs mutation | `test_inheritance_art142_dispossession` | Pure Unit | (a) Female co-heir never in sole possession challenging mutation; (b) Co-heir in possession subjected to ouster. | In (a), Art 142 rejected (no dispossession); In (b), Art 142 applied from date of actual ouster. | **Contract-Specified (Pending Authorization)** |
| **AC-23** | Section 18 statutory fraud requirements | `test_inheritance_section18_fraud` | Pure Unit | Knowledge kept away by fraud or document fraudulently concealed vs bare non-communication of mutation. | Time runs from discovery upon proof of statutory fraud/concealment; bare non-communication fails. | **Contract-Specified (Pending Authorization)** |
| **AC-24** | Two-step Benami Act Section 2(8) classification | `test_benami_sections_and_fiduciary` | Controlled Integration | (a) Wife self-funded purchase; (b) Genuine fiduciary meeting (ii); (c) Wife holding property funded by husband without joint ownership; (d) Business partner without fiduciary duty. | (a) `BENAMI_DEFINITION_NOT_ESTABLISHED`; (b) `BENAMI_EXCEPTION_ESTABLISHED`; (c) & (d) `POTENTIAL_BENAMI_TRANSACTION`. | **Contract-Specified (Pending Authorization)** |
| **AC-25** | Section 489-F mens rea at cheque issuance & forum selection | `test_s489f_cumulative_ingredients` | Pure Unit | (a) Advance contingent guarantee; (b) Dishonest cheque for crystallized debt (`2010 SCMR 806`); (c) Private commercial dispute recovery. | In (a), S.489-F rejected; in (b), S.489-F admitted; in (c), routed to Civil Court S.9/Order XXXVII CPC, NOT Banking Court. | **Contract-Specified (Pending Authorization)** |
| **AC-26** | Section 420 inception-intention test | `test_s420_inception_intention` | Pure Unit | Commercial contract breach without fraudulent inducement at inception (`1999 SCMR 1214`). | FIR quashment admitted to Bucket 1B; criminal cheating rejected. | **Contract-Specified (Pending Authorization)** |
| **AC-27** | Section 406 entrustment versus debtor-creditor | `test_s406_debtor_creditor_entrustment` | Pure Unit | Purchase of goods on credit with default in repayment (`PLD 2004 SC 460`). | Criminal breach of trust rejected; debtor-creditor relationship verified. | **Contract-Specified (Pending Authorization)** |
| **AC-28** | Amended Art 189 FCC/SC precedent binding ratio | `test_amended_art189_precedent_binding` | Pure Unit | (a) FCC ruling deciding legal ratio vs SC ruling; (b) FCC ruling lacking nexus; (c) Ambiguous overlapping scope. | In (a), FCC ratio binds SC; in (b), SC controls only if independently on point; in (c), returns `UNRESOLVED_APEX_PRECEDENTIAL_CONFLICT`. | **Contract-Specified (Pending Authorization)** |
| **AC-29** | Deployed request recount & non-ASCII boundaries | `test_native_tokenizer_full_payload_boundary` | Controlled Integration | Serialized request with message framing, Urdu legal text, XML tags; native tokenizer execution; recount. | Context window ceiling $\le 7,000$ strictly enforced; concatenation boundary verified; non-ASCII handled. | **Contract-Specified (Pending Authorization)** |
| **AC-30** | Benchmark dual-denominator & ground-truth protocol | `test_benchmark_reproducibility_denominator` | Live Pipeline | 30 queries evaluated across: (a) top-10 positions ($N_{\text{queries}}=30$); (b) top-5 positions ($N_{\text{evaluated}}=150$). | Evaluates Macro-Recall@10 = 100%, HitRate@10 = 100%, and Contamination $\le 5/150$ with independent reporting. | **Gated / Pending Authorization** |

---

## 7. Standing Invariants & Pre-Authorization Sign-Off Gate

The execution remains completely stopped under these strict invariants:
1. **Zero Production Code Edits:** `main.py` and `legal_ai/retrieval/unified_orchestrator.py` remain untouched.
2. **Zero Premature Implementation:** `core/post_rerank_domain_gate.py` has not been authored.
3. **Zero Vector Index Modifications:** Pinecone database (401,351 vectors) remains unmodified.
4. **Zero Supabase Schema Migrations:** Database schema and indexes remain unmodified.
5. **Phase 4, Step 5 Implementation Status:** **PAUSED — Awaiting Explicit User Authorization.**
6. **Phase 4, Step 6 Status:** **STRICTLY BLOCKED / UNAUTHORIZED.**
