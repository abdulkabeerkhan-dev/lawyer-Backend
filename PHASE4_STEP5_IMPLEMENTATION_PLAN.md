# Phase 4, Step 5: Implementation Plan & Pre-Authorization Verification Dossier

**Document Version:** 1.7.0 (Comprehensive Pre-Authorization Edition — Full S.2(8)(A)–(D) Benami Tree, Reproducible Art 212 Enactment Inventory, Multi-Factor S.489-F Mens Rea & Forum Separation, Residuary Hierarchy Art 120/142, Reconciled Art 189 Precedence, Supported Deployment Models (GPT-4o / Gemini 2.5 Pro) with Atomic Truncation, Fixed Option A Benchmark Denominator & Seven-Tier Evidentiary Classification)  
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
| **Document Version** | `1.7.0` |
| **Committed File Path** | `PHASE4_STEP5_IMPLEMENTATION_PLAN.md` |
| **Target Repository** | `lawyer-Backend-master` |
| **Active Git Branch** | `feat/phase4-step1-planner` |
| **Specification Baseline Hash** | `8716463` (`PHASE4_STEP5_DOMAIN_GATE_SPECIFICATION.md` v1.4.0) |
| **Audit Baseline Hash** | `8716463` (`PHASE4_STEP5_FINAL_VERIFICATION_AUDIT.md` v1.3.0) |
| **Commit History Chain** | `50e3a60` (v1.0.0) -> `4c7a9b1` (v1.1.0) -> `7873dbf` (v1.2.0) -> `3e0eea0` (v1.3.0) -> `81fd760` (v1.4.0) -> `d837884` (v1.5.0) -> `6787c3f` (v1.6.0) -> Pending (v1.7.0) |
| **SHA-256 Checksum** | Computed upon commit of Version 1.7.0 |
| **Implementation Status** | **WITHHELD / PAUSED — Awaiting Explicit Go-Ahead** |

### 1.2 Seven-Tier Evidentiary Classification Scheme
In accordance with your explicit evidentiary standard, all claims, criteria, and metrics are classified across seven unambiguous states:
1. **`SOURCE_IDENTIFIED`**: Primary statutory provision or judicial report identified by citation and date.
2. **`SOURCE_TEXT_RETRIEVED`**: Authentic official text extracted from Pakistan Code or official law reports.
3. **`SOURCE_AUTHENTICITY_VERIFIED`**: Provision cross-checked against current amendment and repeal status.
4. **`LEGAL_PROPOSITION_REVIEWED`**: Substantive ratio or doctrine formally articulated and reviewed in contract.
5. **`TEST_IMPLEMENTED`**: Executable test code authored and committed in repository test suite.
6. **`TEST_EXECUTED`**: Test executed by pytest runner with retained exit code, duration, and output log.
7. **`INDEPENDENTLY_REPRODUCED`**: Execution independently reproduced in a controlled runtime environment.

*Current Repository Execution Status:*
- **AC-15 (Legacy Regression Suite):** **`TEST_EXECUTED` (100% Passed, 102/102 in 32.55s, Exit Code 0)**.
- **AC-01 through AC-14, AC-16 through AC-30:** **`LEGAL_PROPOSITION_REVIEWED` (Contract-Specified; 0.0% `TEST_EXECUTED` pending implementation authorization)**.

---

## 2. Independent Source-Level Legal & Statutory Verification

### 2.1 Reconciled Legal Doctrine Matrix

| Doctrine Contract ID | Core Legal Proposition | Controlling Primary Authorities | Governing Statutory Anchors | Scope & Non-Applicability Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **`DOCTRINE_ART_212_SERVICE_BAR`** | Four-stage competence gate with reproducible enactment inventory across Federal and Provincial jurisdictions: Constitutional authorization (Art 212(1)(a)-(c)), actual statutory tribunal establishment, subject-matter competence, and Art 212(2) ouster (with provincial proviso). | `2025 SCMR 134` (*Muhammad Hassanullah*), paras 4–6 (Isa CJ, Khan J, Minallah J). | Arts 212(1)(a)-(c), 212(2) Constitution; Federal S.4 FST Act 1973; Provincial Service Tribunals Acts; S.9 CPC 1908. | Evaluates actual tribunal establishment against verified statutory inventory. If no tribunal is established under Art 212(1)(b) for public torts, or if enactment inventory is incomplete, engine returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES` or `JURISDICTION_UNRESOLVED`. Ordinary civil courts retain plenary jurisdiction under S.9 CPC. Tort claims are never routed to Service Tribunals absent express statutory mandate. |
| **`DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT`** | Tripartite rule separating inception fraud, commercial debt vs entrustment, and discretionary pre-challan quashment. | (1) S.420: `1999 SCMR 1214`, `PLD 2005 SC 470`<br/>(2) S.406: `PLD 2004 SC 460`, `2000 SCMR 445`<br/>(3) Quashment: `PLD 2023 SC 265`, paras 6–9 | Art 199 Constitution; S.561-A CrPC; Ss.405, 406, 415, 420 PPC. | Commercial breach without inception fraud cannot be criminalized. Pre-challan FIR quashment under Art 199 is discretionary and exceptional; S.561-A applies to pending judicial proceedings. |
| **`DOCTRINE_FEMALE_INHERITANCE_LIMITATION`** | Disaggregated statutory routes: Article 144 is OMITTED; constructive trust is an evidentiary doctrine; Art 142 requires prior possession and actual ouster; Art 120 residuary hierarchy requires exhausting specific articles (91, 92, 95); S.18 strictly follows statutory fraud; S.9 continuous time. | `1991 SCMR 2063` (Art 144 omission);<br/>`PLD 1990 SC 1` (*Ghulam Ali*), pp. 14–19;<br/>`PLD 2023 SC 362` (*Saadat Khan*), paras 7–10 | Limitation Act 1908 (Arts 91, 92, 95, 120, 142, Ss.6, 9, 14, 18, 29); Limitation (Amendment) Act 1995 (Act II of 1995); S.41 TPA 1882. | Article 144 omitted by Act II of 1995. Adverse possession cannot extinguish title. Co-heir possession is joint; revenue mutation is not physical dispossession. Art 142 requires prior possession and actual ouster. Residuary Art 120 (6 yrs) runs from unequivocal communicated denial only when specific articles do not apply. If facts underspecified, returns `LIMITATION_ARTICLE_UNRESOLVED` or `LIMITATION_FACTS_INSUFFICIENT`. |
| **`DOCTRINE_BENAMI_PARTITION_BAR`** | Complete statutory classification tree evaluating independent limbs under Section 2(8)(A), (B), (C), and (D); conditional exception numbering under Section 2(8)(A)(b)(i)-(iv); separation of classification from adjudication and confiscation. | `2023 SCMR 572` (*Muhammad Yousaf*), CA 801/2021 decided Dec 14, 2022;<br/>`1989 SCMR 130` | Benami Transactions (Prohibition) Act 2017 (Ss.2(8)(A)-(D), 3, 4, 5, 24, 25, 51); S.41 TPA 1882; Art 117 QSO 1984. | Independent evaluation of 2(8)(A)-(D). Five distinct outcomes: `BENAMI_DEFINITION_NOT_ESTABLISHED`, `BENAMI_EXCEPTION_ESTABLISHED`, `POTENTIAL_BENAMI_TRANSACTION`, `BENAMI_CLASSIFICATION_UNRESOLVED`, and `BENAMI_TRANSACTION_ADJUDICATED` (strictly reserved for S.24 formal findings). Confiscation and criminal sanctions are never inferred by retrieval. Pre-2017 ancestral acquisitions evaluated under multi-factor proof. |
| **`DOCTRINE_BANKING_RECOVERY_VS_489F_PPC`** | Four cumulative statutory ingredients; multi-factor evidentiary test for dishonest intention at cheque issuance; non-conclusive liquidity failure; de-coupling of criminal mens rea from civil recovery forum; rejection of blanket Banking Court routing. | `2010 SCMR 806` (*Muhammad Sultan v. State*), paras 8–10 (Tariq Parvez J, Nasir-ul-Mulk J, Amir Hani Muslim J). | Financial Institutions (Recovery of Finances) Ordinance 2001 (Ss.2(d), 9, 22); S.489-F PPC; S.9 CPC 1908; Order XXXVII CPC. | Inquires into dishonest intention at the time of issuing the cheque. Merely labeling a cheque "security" does not bar S.489-F if an existing crystallized obligation existed. Liquidity failure is evidentiary, not an automatic defense. Forum selection for civil recovery is strictly conditional: Banking Court under FIO 2001 applies only to financial institutions and customer finance; private commercial disputes lie before ordinary Civil Courts under S.9 or Order XXXVII CPC. |

---

### 2.2 Detailed Doctrinal and Statutory Specifications

#### 1. Contract 1: `DOCTRINE_ART_212_SERVICE_BAR` (Reproducible Enactment Inventory & Competence Gate)
The engine executes a **four-stage constitutional and statutory competence gate** supported by an independently reproducible statutory enactment inventory:

##### Complete Reproducible Statutory Enactment Inventory (Verified October 31, 2026)

| Jurisdiction | Enactment Title & Citation | Key Statutory Provisions | Current Status | Official Source Baseline | Result & Adjudicatory Scope |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Federal** | Service Tribunals Act, 1973 (Act LXX of 1973) | Sections 3 (Establishment), 4 (Appeals regarding terms and conditions), 5 (Powers of Tribunal) | In force as amended by Act XVII of 2014 & Act XXVI of 2020 | Pakistan Code (`pakistancode.gov.pk`) | Exclusive jurisdiction strictly over civil servants' terms and conditions (Article 212(1)(a)). Confers **zero** jurisdiction over public torts or enemy property. |
| **Punjab** | Punjab Service Tribunals Act, 1974 (Punjab Act IX of 1974) | Sections 3 (Establishment), 4 (Appeals by civil servants), 5 (Powers) | In force as amended | Punjab Laws (`punjablaws.gov.pk`) | Exclusive jurisdiction strictly over Punjab civil servants' terms and conditions. Confers **zero** jurisdiction over public torts or enemy property. |
| **Sindh** | Sindh Service Tribunals Act, 1973 (Sindh Act I of 1973) | Sections 3 (Establishment), 4 (Appeals) | In force as amended | Sindh Laws (`sindhlaws.gov.pk`) | Exclusive jurisdiction strictly over Sindh civil servants' terms and conditions. Confers **zero** jurisdiction over public torts or enemy property. |
| **Khyber Pakhtunkhwa** | Khyber Pakhtunkhwa Service Tribunals Act, 1974 (KP Act I of 1974) | Sections 3 (Establishment), 4 (Appeals) | In force as amended | KP Code (`kpcode.gov.pk`) | Exclusive jurisdiction strictly over KP civil servants' terms and conditions. Confers **zero** jurisdiction over public torts or enemy property. |
| **Balochistan** | Balochistan Service Tribunals Act, 1974 (Balochistan Act V of 1974) | Sections 3 (Establishment), 4 (Appeals) | In force as amended | Balochistan Code | Exclusive jurisdiction strictly over Balochistan civil servants' terms and conditions. Confers **zero** jurisdiction over public torts or enemy property. |
| **Federal / Provincial (Public Torts)** | Article 212(1)(b) Administrative Courts / Tribunals | None enacted | **Not Enacted** | Exhaustive search of Pakistan Code and provincial statute books | **No Administrative Court or Tribunal has been enacted or established under Article 212(1)(b)**. Status: `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`. |
| **Federal (Enemy Property)** | Enemy Property (Continuance of Emergency Provisions) Ordinance, 1969 (Ordinance I of 1969) | Sections 2, 3, 4 (Appointment of Custodian, Vesting of Property) | In force | Pakistan Code (`pakistancode.gov.pk`) | Establishes an executive Custodian under administrative control; **no judicial administrative tribunal established under Article 212(1)(c)**. Status: `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`. |

##### Four-Stage Gate Logic with Explicit Fallback States
1. **Stage 1 (Constitutional Head):** Matches subject matter to Article 212(1)(a), (b), or (c).
2. **Stage 2 (Actual Statutory Establishment):** Queries the verified enactment inventory. If no established tribunal exists for that head (e.g. public torts), the engine sets status `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`. The Article 212(2) bar cannot operate. Plenary jurisdiction remains with ordinary civil courts under Section 9 CPC. The engine **never routes tort claims to Service Tribunals**.
3. **Stage 3 (Tribunal Statutory Competence):** Where a tribunal exists (e.g. FST), verifies all statutory requirements under Section 4 FST Act 1973: (1) claimant is a civil servant under Section 2(1)(b) CSA 1973; (2) final departmental order; (3) grievance affects terms and conditions; (4) departmental appeal exhausted. If any condition is missing, returns `FST_JURISDICTION_INCOMPLETE`.
4. **Stage 4 (Article 212(2) Ouster & Proviso):** Ouster applies only where Stage 2 and Stage 3 are satisfied (*Muhammad Hassanullah*, `2025 SCMR 134`). For provincial tribunals, requires verified provincial resolution and parliamentary extension Act.
5. **Fallback States:**
   - If statutory inventory is incomplete or research route ambiguous $\rightarrow$ `JURISDICTION_UNRESOLVED`.
   - Non-civil servant government contractor $\rightarrow$ `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL` (Article 199 writ is not automatically admitted; remains subject to alternative remedies under Section 9 CPC, arbitration clauses, and disputed factual questions).

---

#### 2. Contract 2: `DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT` (Tripartite Penal Separation)
The engine executes a three-part doctrinal analysis separating civil debt from criminal liability:
* **Rule 2A (Section 420 PPC — Inception of Intention):**
  - Section 420 PPC requires dishonest intention **at the time of making the representation or inducement**. Subsequent contractual failure or commercial breach does not constitute cheating.
  - Anchored in Supreme Court landmarks: **`1999 SCMR 1214`** (*Zafar Iqbal v. State*) and **`PLD 2005 SC 470`** (*Muhammad Khalid v. State*).
* **Rule 2B (Section 406 PPC — Commercial Debt vs. Entrustment):**
  - Section 406 PPC requires entrustment in a fiduciary capacity under Section 405 PPC. Commercial sale on credit or advance loans creates an ordinary debtor-creditor relationship, not criminal breach of trust.
  - Anchored in Supreme Court landmarks: **`PLD 2004 SC 460`** (*Muhammad Rafique v. State*) and **`2000 SCMR 445`** (*Mirza Naseem Baig v. State*).
* **Rule 2C (Article 199 Constitutional Quashment vs. Section 561-A CrPC):**
  - Quashing of a pre-challan FIR under Article 199 is an **extraordinary, discretionary constitutional remedy**, governed by **`PLD 2023 SC 265`** (*Director General, FIA v. Syed Hamid Ali Shah*, paras 6–9), granted where the FIR discloses no cognizable criminal offence or represents an abuse of police process. Section 561-A CrPC governs proceedings pending before trial courts.

---

#### 3. Contract 3: `DOCTRINE_FEMALE_INHERITANCE_LIMITATION` (Omission of Art 144, Art 142 Criteria, Residuary Hierarchy Art 120 & Statutory S.18)
The engine executes a disaggregated statutory analysis:
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
       - Article 142 (possession after dispossession: 12 years from dispossession).
    3. *Residuary Gate:* Only when no specific article applies does Article 120 govern.
    4. *Accrual & Statutory Savings:* Under *Saadat Khan v. Shahid-Ur-Rehman* (`PLD 2023 SC 362`, paras 7–10), right to sue accrues upon **unequivocal communicated denial or overt hostile act** (Date $D$). The engine evaluates statutory savings: Section 6 (disability/minority), Section 9 (continuous running of time), Section 14 (bona fide litigation in wrong forum), Section 18 (fraudulent concealment of right/document), and Section 29 (savings).
    5. *Underspecified States:* If relief or facts are insufficient to establish the governing article or date of accrual, the engine returns `LIMITATION_ARTICLE_UNRESOLVED` or `LIMITATION_FACTS_INSUFFICIENT`, strictly avoiding forced Article 120 outcomes.
* **Section 18 — Statutory Fraud & Fraudulent Concealment:**
  - Faithfully enforces the statutory text of Section 18: Where fraud has kept a person from knowledge of their right or title, or where a necessary document has been fraudulently concealed, time is computed from when the fraud first became known, or when the document could first be produced. Avoids non-statutory "active vs passive" criteria.

---

#### 4. Contract 4: `DOCTRINE_BENAMI_PARTITION_BAR` (Full Section 2(8)(A)–(D) Classification Tree)
The engine executes a **comprehensive statutory classification tree** evaluating all four independent limbs of Section 2(8) of the **Benami Transactions (Prohibition) Act, 2017**:

```
[Candidate Transaction Evaluation]
       |
       +---> [Limb 1: Section 2(8)(A) - Consideration & Beneficial Interest]
       |       - Did Person A provide/pay consideration?
       |       - Is property transferred to / held by Person B?
       |       - Is property held for immediate/future benefit of Person A?
       |       |
       |       +---> If NO: Section 2(8)(A) definition NOT met.
       |       +---> If YES: Evaluate Section 2(8)(A)(b) Statutory Exceptions:
       |               * (b)(i): HUF Karta / member.
       |               * (b)(ii): Person in genuine fiduciary capacity (trustee, executor, partner, director, depository agent).
       |               * (b)(iii): Spouse or child (conditionally requires: (1) consideration from known resources of individual AND (2) individual appeared as joint owner).
       |               * (b)(iv): Brother, sister, lineal ascendant/descendant (conditionally requires: (1) names appear as joint owners AND (2) consideration from known resources).
       |               |
       |               +---> Exception Satisfied? ---> BENAMI_EXCEPTION_ESTABLISHED
       |               +---> Exception Fails?    ---> POTENTIAL_BENAMI_TRANSACTION (under Limb A)
       |
       +---> [Limb 2: Section 2(8)(B) - Fictitious Name]
       |       - Was transaction conducted in a fictitious / non-existent name?
       |       +---> If YES: POTENTIAL_BENAMI_TRANSACTION (under Limb B)
       |
       +---> [Limb 3: Section 2(8)(C) - Owner Unaware or Denies Ownership]
       |       - Is registered owner unaware of, or does owner deny, ownership?
       |       +---> If YES: POTENTIAL_BENAMI_TRANSACTION (under Limb C)
       |
       +---> [Limb 4: Section 2(8)(D) - Untraceable / Fictitious Consideration Provider]
               - Is the person providing consideration untraceable or fictitious?
               +---> If YES: POTENTIAL_BENAMI_TRANSACTION (under Limb D)

[Final Classification Synthesis]
  - All Limbs (A), (B), (C), (D) Not Established ------> BENAMI_DEFINITION_NOT_ESTABLISHED
  - Limb (A) Established AND Exception Satisfied ------> BENAMI_EXCEPTION_ESTABLISHED
  - Any Limb (A)-(D) Established AND No Exception -----> POTENTIAL_BENAMI_TRANSACTION
  - Evidence Incomplete on Consideration/Ownership ---> BENAMI_CLASSIFICATION_UNRESOLVED
  - Section 24 Adjudicating Authority Formal Order ----> BENAMI_TRANSACTION_ADJUDICATED
```

* **Core Principles & Procedural Separation:**
  - A transaction where a wife holds property in her sole name is **never labeled benami solely because the joint-ownership condition of Exception (b)(iii) is absent**. If the wife provided consideration herself, or if the husband purchased it as an outright, irrevocable gift without retained benefit, Limb (A) definition is not established (`BENAMI_DEFINITION_NOT_ESTABLISHED`).
  - *Separation of Statutory Stages:* The retrieval engine strictly distinguishes:
    1. Section 2(8) statutory classification;
    2. Section 3 statutory prohibition;
    3. Section 24 formal adjudication before the Adjudicating Authority;
    4. Section 25 confiscation by the Federal Government;
    5. Section 51 criminal sanctions before the Special Court.
    The engine **never infers confiscation or criminal liability merely from a potential Section 2 classification**.
  - Substantive prohibitions (Sections 3, 4, 5) operate prospectively and do not extinguish pre-existing vested private rights in ancestral partition suits (*Muhammad Yousaf v. Muhammad Ishaq Rana*, `2023 SCMR 572`, CA 801/2021 decided Dec 14, 2022). Pre-2017 ancestral acquisitions are evaluated under the multi-factor evidentiary test (`1989 SCMR 130`).

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

## 3. Constitutional & Precedential Hierarchy Verification

### 3.1 Twenty-Seventh Constitutional Amendment (2025) & Operative Article 189
Under Pakistan's **Constitution (Twenty-Seventh Amendment) Act, 2025**, Article 189 was substituted:
> *(1) Any decision of the Federal Constitutional Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan, including the Supreme Court.*  
> *(2) Subject to clause (1), any decision of the Supreme Court shall, to the extent that it decides a question of law or is based upon or enunciates a principle of law, be binding on all other courts in Pakistan.*

### 3.2 Structured Precedence Algorithm with Ratio Applicability
The engine evaluates precedent through a five-stage pipeline:
1. **Direct Institutional Apex Authority (Amended Article 189):**
   - Decisions of the Federal Constitutional Court (FCC) deciding a question of law or enunciating a principle of law bind all other courts in Pakistan, including the Supreme Court.
   - **No Intra-Court Bench-Strength Tie-Breaker Across Tiers:** A lower court or search engine cannot use an SC decision—even by a larger bench—to overrule an FCC decision deciding that question of law. Institutional hierarchy strictly controls over intra-court bench strength.
2. **Material Ratio Identification & Nexus Evaluation:**
   - The engine establishes whether the FCC decision actually determines the specific question of law presented in the query.
   - *Lack of Nexus:* If an FCC decision determines a question lacking material identity with the query (e.g. an FCC ruling on constitutional delimitation cited in a private property partition), it is classified as `NON_CONTROLLING_DUE_TO_ABSENCE_OF_NEXUS`.
   - *Independent SC Precedent Evaluation:* An SC decision controls in such a case **only if it independently supplies an applicable legal ratio directly on point**, not by virtue of displacing the FCC decision.
3. **Controlling Hierarchy Application:**
   - Where an applicable FCC ratio clearly determines the legal point, the engine applies that ratio directly. A conflict is not escalated merely because an earlier or larger SC bench expressed a different view prior to the constitutional amendment.
4. **Intra-Tier Bench Strength (*Multiline Associates*, `1995 SCMR 362`):**
   - Operates strictly *within* the same judicial institution (e.g. SC 5-member bench controls over SC 3-member bench). Co-equal benches cannot overrule each other.
5. **Apex Scope Conflict Escalation:**
   - The engine returns typed status `UNRESOLVED_APEX_RATIO_SCOPE` **only when the substantive scope, ratio, or applicability of competing apex authorities cannot be reliably reconciled through statutory interpretation**.

---

## 4. Tokenizer Architecture: Supported Deployments & Atomic Truncation

### 4.1 Supported Production Deployments & Lifecycle Records (October 2026 Baseline)
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

---

## 5. Disaggregated Retrieval Quality & Option A (Fixed Denominator) Benchmark Protocol

The benchmark harness enforces exact, independent definitions and adopts **Option A (Fixed Denominator)** to guarantee absolute mathematical reproducibility:

### 5.1 Macro-Averaged Recall@10 (AC-13)
* **Measurement Population:** Query-level evaluation across all $N_{\text{queries}} = 30$ standardized benchmark queries.
* **Gold-Standard Set Requirement:** Every query $q$ must possess an authenticated, non-empty set of relevant primary legal authorities: $|\text{Gold}_q| \ge 1$.
* **Per-Query Recall Formulation:**
  $$\text{Recall@10}_q = \frac{|\text{Gold}_q \cap \text{Top10}_q|}{|\text{Gold}_q|}$$
* **Macro-Averaged Metric:**
  $$\text{Macro-Recall@10} = \frac{1}{30} \sum_{q=1}^{30} \text{Recall@10}_q = 100.0\%$$
* **Distinct Hit Rate@10 Metric (Reported Separately):**
  $$\text{HitRate@10} = \frac{1}{30} \sum_{q=1}^{30} \mathbb{I}(|\text{Gold}_q \cap \text{Top10}_q| \ge 1) = 100.0\%$$

### 5.2 Option A (Fixed Denominator) Contamination Protocol (AC-14)
* **Fixed Population Requirement:** Every query $q \in \{1 \dots 30\}$ is strictly required to return at least 5 candidates in its evaluated set. If any query returns fewer than 5 candidates, the benchmark halts immediately with failure code `BENCHMARK_INSUFFICIENT_CANDIDATES`.
* **Exact Evaluated Denominator ($N_{\text{evaluated}}$):**
  $$N_{\text{evaluated}} = 30 \text{ queries} \times 5 \text{ positions} = 150 \text{ positions strictly}$$
* **Exact Contamination Formulation:**
  $$\text{Contamination Rate} = \frac{\sum_{q=1}^{30} \sum_{k=1}^{5} \mathbb{I}(c_{q,k} \in \text{OffDomainPool})}{150} \le \frac{5}{150} = \frac{1}{30} \approx 3.333\%$$
  - Maximum permitted off-domain candidates across the entire benchmark is **strictly 5 positions out of 150**.
  - Any run with 6 or more off-domain candidates fails the benchmark.
* **Benchmark Provenance Manifest (AC-30):** The harness retains: (1) exact 30 queries; (2) gold-standard citation mappings; (3) raw top-10 and top-5 retrieved IDs; (4) model and evaluator versions; (5) per-query recall; and (6) per-query contamination counts.

---

## 6. Extended Acceptance Criteria Matrix (AC-01 through AC-30)

| Criteria ID | Scope of Requirement | Target Test Identifier | Test Tier | Fixtures, Negative Conditions & Forum Logic | Expected Assertion & Result | Evidentiary Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Gate interface contract v1.7.0 | `test_domain_gate_interface_contract` | Pure Unit | Valid candidate list + query plan passed to `partition_candidates_into_ranking_buckets()`. | Returns partitioned buckets; zero schema deviations; telemetry populated. | **Contract-Specified (Pending Authorization)** |
| **AC-02** | Domain classification fixtures | `test_domain_classification_positive_negative` | Pure Unit | Synthetic on-domain civil case vs off-domain family dower case (`2015 SCMR 869`). | On-domain placed in Bucket 1A; off-domain placed in Bucket 3. | **Contract-Specified (Pending Authorization)** |
| **AC-03** | Statutory fallback 5-stage order | `test_statutory_fallback_five_stage_order` | Pure Unit | Direct statute match, secondary safe statute, foreign statute, unannotated procedural, ambiguous. | Direct $\rightarrow$ 1A; Foreign $\rightarrow$ 3; Procedural $\rightarrow$ 2; Ambiguous $\rightarrow$ Dropped. | **Contract-Specified (Pending Authorization)** |
| **AC-04** | Interdisciplinary doctrine contracts | `test_doctrine_contracts_positive_negative` | Pure Unit | 5 Positive fixtures (`2025 SCMR 134`, `1999 SCMR 1214`, `PLD 1990 SC 1`, `2023 SCMR 572`, `2010 SCMR 806`) + 5 Negative fixtures. | Positive admitted to Bucket 1B (`APPROVED_CROSS_DOMAIN`); Negative demoted to Bucket 3. | **Contract-Specified (Pending Authorization)** |
| **AC-05** | Quarantine boundary | `test_quarantine_hard_drop_top_scoring` | Pure Unit | Candidate marked `is_quarantined=True` with highest cross-encoder score ($0.95$). | Candidate hard-dropped to `dropped_pool`; zero presence in context assembly output. | **Contract-Specified (Pending Authorization)** |
| **AC-06** | Strict mode generation boundary | `test_strict_mode_generation_boundary` | Pure Unit | Diagnostic caller sets `strict_mode=False`. | Bucket 3 candidates returned in telemetry only; strictly excluded from `assembled_context`. | **Contract-Specified (Pending Authorization)** |
| **AC-07** | Authority hierarchy (Amended Art 189) | `test_constitutional_hierarchy_subject_matter` | Pure Unit | (a) FCC ruling on legal ratio vs SC ruling on same point; (b) FCC ruling lacking nexus; (c) Unreconciled overlap. | In (a), FCC ratio binds SC; in (b), SC controls only if independently on point; in (c), returns `UNRESOLVED_APEX_RATIO_SCOPE`. | **Contract-Specified (Pending Authorization)** |
| **AC-08** | Pure relevance floor ($S_{\text{rerank}} \ge 0.35$) | `test_pure_relevance_floor_cutoff` | Pure Unit | Apex Supreme Court candidate with $S_{\text{rerank}} = 0.31 < 0.35$. | Excluded at Step 3 of context assembly; status `BELOW_RELEVANCE_FLOOR`. | **Contract-Specified (Pending Authorization)** |
| **AC-09** | Canonical appeal deduplication | `test_canonical_appeal_deduplication` | Pure Unit | Two records representing same judgment (Civil Appeal 801/2021) from different law reports. | Merged into single canonical record preserving highest score; distinct appeals preserved. | **Contract-Specified (Pending Authorization)** |
| **AC-10** | Native generation tokenizer contract | `test_native_tokenizer_contract_and_abort` | Controlled Integration | Pinned `tiktoken==0.7.0` attached; simulated outage (`allow_unverified_fallback=False`). | Normal: returns `SUCCESS` exact count; Outage: returns `TOKENIZER_UNAVAILABLE_ABORT`. | **Contract-Specified (Pending Authorization)** |
| **AC-11** | Atomic legal-passage assembly & output cap | `test_assembly_truncation_and_payload_invariant` | Controlled Integration | Atomic legal blocks evaluated against remaining budget $\Delta$; generation cap parameter (`max_tokens=1000`). | Blocks fit atomically or dropped entirely (`ATOMIC_BLOCK_BUDGET_OVERFLOW`); output cap verified; $T_{\text{prompt}} \le 7,000$. | **Contract-Specified (Pending Authorization)** |
| **AC-12** | Gold-standard benchmark evaluator | `test_benchmark_evaluator_doctrine_awareness` | Controlled Integration | Benchmark script runs over test fixtures with cross-domain doctrine candidates. | Evaluator correctly scores Bucket 1B candidates as relevant without false contamination. | **Contract-Specified (Pending Authorization)** |
| **AC-13** | Retrieval Quality (Macro-Recall@10 = 100%) | `test_live_benchmark_recall` | Live Pipeline | 30 queries evaluated at top-10 positions against authenticated non-empty gold sets ($|\text{Gold}_q| \ge 1$). | Macro-Recall@10 verified at 100.0%; HitRate@10 reported at 100.0%. | **Gated / Pending Authorization** |
| **AC-14** | Contamination Bound ($\le 5/150$) | `test_live_benchmark_contamination` | Live Pipeline | 30 queries evaluated at top-5 positions (Option A: $N_{\text{evaluated}} = 150$ strictly). | Contamination strictly $\le 5/150 \approx 3.333\%$. Run halts if any query returns $< 5$ candidates. | **Gated / Pending Authorization** |
| **AC-15** | Regression test preservation | Pytest 11 test modules | Pure Unit & Integration | 11 legacy test files executed in repository workspace with `$env:PYTHONPATH="."`. | **102 passed, 6 warnings in 32.55s (100.0%)**. Confirms 0 legacy regressions. | **TEST_EXECUTED (100% Passed)** |
| **AC-16** | Traceable candidate audit trail | `test_candidate_audit_trail_telemetry` | Pure Unit | Candidate list processed through `assemble_generation_context()`. | Audit report contains traceable inclusion/exclusion reason for every evaluated candidate. | **Contract-Specified (Pending Authorization)** |
| **AC-17** | Article 212(1)(a) service-condition jurisdiction | `test_art212_service_conditions` | Pure Unit | (a) Civil servant challenging departmental promotion order (`2025 SCMR 134`); (b) Non-civil servant contractor. | In (a), Article 199 barred $\rightarrow$ Bucket 1B FST; in (b), returns `SERVICE_TRIBUNAL_JURISDICTION_EXCLUDED; WRIT_MAINTAINABILITY_CONDITIONAL`. | **Contract-Specified (Pending Authorization)** |
| **AC-18** | Article 212(1)(b) public-service tort competence gate | `test_art212_tort_jurisdiction` | Pure Unit | (a) Tort claim against Government where enactment inventory shows NO Art 212(1)(b) tribunal; (b) Disguised service claim. | In (a), returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`, routes to civil court S.9 CPC; in (b), verifies all S.4 FST conditions. | **Contract-Specified (Pending Authorization)** |
| **AC-19** | Article 212(1)(c) enemy-property jurisdiction | `test_art212_enemy_property` | Pure Unit | Dispute concerning enemy property custody under 1969 Ordinance. | Returns `TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES`, evaluated under administrative regulations, NOT FST. | **Contract-Specified (Pending Authorization)** |
| **AC-20** | Article 212(2) provincial extension proviso | `test_art212_provincial_proviso` | Pure Unit | Provincial service tribunal candidate where parliamentary extension Act is enacted vs absent. | Art 212(2) bar applies only where extension Act enacted; otherwise evaluated under provincial law. | **Contract-Specified (Pending Authorization)** |
| **AC-21** | Residuary Article 120 inheritance limitation & accrual | `test_inheritance_art120_denial` | Pure Unit | (a) Instrument cancellation pleaded; (b) Underspecified relief; (c) Clear declaration with unequivocal denial on Date $D$. | In (a), Art 91 evaluated; in (b), `LIMITATION_ARTICLE_UNRESOLVED`; in (c), residuary Art 120 applied strictly from Date $D$. | **Contract-Specified (Pending Authorization)** |
| **AC-22** | Article 142 dispossession & ouster vs mutation | `test_inheritance_art142_dispossession` | Pure Unit | (a) Female co-heir never in sole possession challenging mutation; (b) Co-heir in possession subjected to ouster. | In (a), Art 142 rejected (no dispossession); In (b), Art 142 applied from date of actual ouster. | **Contract-Specified (Pending Authorization)** |
| **AC-23** | Section 18 statutory fraud requirements | `test_inheritance_section18_fraud` | Pure Unit | Knowledge kept away by fraud or document fraudulently concealed vs bare non-communication of mutation. | Time runs from discovery upon proof of statutory fraud/concealment; bare non-communication fails. | **Contract-Specified (Pending Authorization)** |
| **AC-24** | Full Section 2(8)(A)-(D) Benami classification tree | `test_benami_sections_and_fiduciary` | Controlled Integration | (a) Wife self-funded purchase; (b) Fiduciary capacity under 2(8)(A)(b)(ii); (c) Fictitious name under 2(8)(B); (d) Husband funded in wife's name without joint ownership; (e) Section 24 formal order. | (a) `BENAMI_DEFINITION_NOT_ESTABLISHED`; (b) `BENAMI_EXCEPTION_ESTABLISHED`; (c) & (d) `POTENTIAL_BENAMI_TRANSACTION`; (e) `BENAMI_TRANSACTION_ADJUDICATED`. | **Contract-Specified (Pending Authorization)** |
| **AC-25** | Section 489-F mens rea at cheque issuance & forum selection | `test_s489f_cumulative_ingredients` | Pure Unit | (a) Existing debt labeled "security"; (b) Pure advance contingent guarantee; (c) Liquidity failure evidence; (d) Private commercial recovery. | In (a), S.489-F admitted; in (b), S.489-F rejected; in (c), weighed as evidence; in (d), routed to Civil Court S.9/Order XXXVII CPC. | **Contract-Specified (Pending Authorization)** |
| **AC-26** | Section 420 inception-intention test | `test_s420_inception_intention` | Pure Unit | Commercial contract breach without fraudulent inducement at inception (`1999 SCMR 1214`). | FIR quashment admitted to Bucket 1B; criminal cheating rejected. | **Contract-Specified (Pending Authorization)** |
| **AC-27** | Section 406 entrustment versus debtor-creditor | `test_s406_debtor_creditor_entrustment` | Pure Unit | Purchase of goods on credit with default in repayment (`PLD 2004 SC 460`). | Criminal breach of trust rejected; debtor-creditor relationship verified. | **Contract-Specified (Pending Authorization)** |
| **AC-28** | Amended Art 189 FCC/SC precedent binding ratio | `test_amended_art189_precedent_binding` | Pure Unit | (a) FCC ruling on property principle vs SC ruling; (b) FCC ruling lacking nexus; (c) Ambiguous overlapping scope. | In (a), FCC ratio binds SC; in (b), SC controls only if independently on point; in (c), returns `UNRESOLVED_APEX_RATIO_SCOPE`. | **Contract-Specified (Pending Authorization)** |
| **AC-29** | Deployed request recount & non-ASCII boundaries | `test_native_tokenizer_full_payload_boundary` | Controlled Integration | Serialized request with message framing, Urdu legal text, XML tags; native tokenizer execution; recount. | Context window ceiling $\le 7,000$ strictly enforced; concatenation boundary verified; non-ASCII handled. | **Contract-Specified (Pending Authorization)** |
| **AC-30** | Benchmark dual-denominator & ground-truth protocol | `test_benchmark_reproducibility_denominator` | Live Pipeline | 30 queries evaluated across: (a) top-10 positions ($N_{\text{queries}}=30$); (b) top-5 positions (Option A: $N_{\text{evaluated}}=150$). | Evaluates Macro-Recall@10 = 100%, HitRate@10 = 100%, and Contamination $\le 5/150$ with independent reporting. | **Gated / Pending Authorization** |

---

## 7. Standing Invariants & Pre-Authorization Sign-Off Gate

The execution remains completely stopped under these strict invariants:
1. **Zero Production Code Edits:** `main.py` and `legal_ai/retrieval/unified_orchestrator.py` remain untouched.
2. **Zero Premature Implementation:** `core/post_rerank_domain_gate.py` has not been authored.
3. **Zero Vector Index Modifications:** Pinecone database (401,351 vectors) remains unmodified.
4. **Zero Supabase Schema Migrations:** Database schema and indexes remain unmodified.
5. **Phase 4, Step 5 Implementation Status:** **PAUSED — Awaiting Explicit User Authorization.**
6. **Phase 4, Step 6 Status:** **STRICTLY BLOCKED / UNAUTHORIZED.**
