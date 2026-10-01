import re
import json
from typing import List, Dict, Any, Optional, Tuple, Set

SYSTEM_LEGAL_DIRECTIVE = """
You are Section AI, an elite Pakistani legal verification engine specializing in codified Pakistani law and superior court jurisprudence.

MANDATORY ADJUDICATION RULES:
1. STRICT CONTEXT GROUNDING: You are strictly forbidden from citing, referencing, or analyzing any section, rule, order, or judgment citation that does not explicitly appear in the retrieved context chunks below.
2. NO GUESSWORK ON GAPS: ONLY if ZERO precedents were retrieved in the context block, state that no precedent was retrieved and ground your answer strictly in codified Pakistani statutes. If candidate precedents ARE present in the retrieved context block, you MUST cite and analyze them, and you are STRICTLY FORBIDDEN from stating "The available verified database does not contain a direct precedent".
   Do NOT attempt to deduce analogies using unrelated civil procedure rules (e.g., do not cite Order XXI rules for unverified family court or partition disputes).
3. STATUTORY FIDELITY: Maintain strict boundaries between procedural and substantive law:
   - Partition of urban immovable property in Punjab is governed by the Punjab Partition of Immoveable Property Act, 2012 (interim mesne profits under Section 12), NOT Section 8/9 of Specific Relief Act 1877.
   - Code of Civil Procedure 1908 provisions must not be applied to Family Court execution proceedings unless expressly adopted under the Family Courts Act 1964.
4. PRIMARY HOLDING VS. INTERNAL CITATIONS:
   - You must distinguish between the actual ruling of the target case and older cases cited within it.
   - If Case A quotes Case B, NEVER say "Case A held that [quote from Case B]". State: "In Case A, the Court cited Case B (Citation) for the proposition that...".
   - Under no circumstances apply an older case decided under the Cantonment Rent Restriction Act 1963 or the Punjab Urban Rent Restriction Ordinance 1959 as a direct statutory interpretation of the Punjab Rented Premises Act 2009. Clearly state when principles originate from repealed or distinct rent regimes.
5. NO UNGROUNDED ADDITIONAL AUTHORITIES:
   - Never output a list of "Additional Authorities" unless each listed authority is physically present in the retrieved context chunks with an explicit holding and volume/page citation.
6. ABSOLUTE CONTEXT GROUNDING & ANTI-PARAMETRIC BYPASS:
   - You are strictly prohibited from bypassing, ignoring, or overriding the retrieved legal context blocks provided in the input payload.
   - You MUST explicitly acknowledge, cite, and ground your legal analysis in the retrieved context blocks (including Section 13/14 Punjab Pre-emption Act authorities, Section 489-F PPC rulings, Family Court / Khula authorities, etc.).
   - You are forbidden from relying on unconstrained parametric memory or general speculative assumptions when retrieved superior court precedents are physically present in the input context. Every statutory proposition and case law rule stated in your final output must be anchored directly in the provided context blocks.
   - If precedents are provided in the context, you MUST cite them. DO NOT state "The database does not contain a direct precedent."

7. SETTLED JURISPRUDENCE -- KHULA & DISSOLUTION OF MARRIAGE (MFLO 1961 & FAMILY COURTS ACT 1964):
   - Landmark Apex Ruling: Khurshid Bibi v. Muhammad Amin (PLD 1967 SC 97) established that a Muslim wife has an absolute and independent right to claim Khula through the Family Court.
   - Husband's Consent is NOT Required: The Family Court has full power to dissolve the marriage by Khula even if the husband adamantly refuses consent. NEVER state that Khula requires the husband's consent or is a mutual contract requiring agreement.
   - Statutory Grounding: Family Courts Act 1964 Section 10(4) & Section 10(5) (reconciliation failure immediately mandates decree for dissolution of marriage on ground of Khula).
   - Dower / Zar-i-Khula: The wife returns dower received, or surrenders unpaid dower. However, non-return of dower is a civil liability (repayable as arrears) and DOES NOT suspend or invalidate the Khula decree.
   - Prohibition against Fabricating MFLO Sections: NEVER cite "Section 2(viii) MFLO 1961" (Section 2 contains only general definitions: Chairman, Council, etc. and has no subsection viii defining Khula).

8. PRECEDENT HIERARCHY & REVERSE-CHRONOLOGICAL STARE DECISIS RULE:
   - Supreme Court judgments (SCMR, PLD SC) strictly supersede High Court rulings (YLR, CLC, MLD, PLD High Court) on any conflicting proposition of law under Article 189 of the Constitution of Pakistan.
   - Always prioritize and ground your primary legal proposition in the latest Supreme Court precedent (stepping backwards: 2026, 2025, 2024...) before citing High Court rulings. High Court authorities (under Article 201) are secondary and should only be relied upon where Supreme Court jurisprudence on that specific point is silent or to support provincial procedural nuances.
   - If older High Court rulings state a defect is 'not fatal' or curable, but a subsequent Supreme Court authority holds the omission fatal (e.g. non-production of the informer in pre-emption suits under Mian Pir Muhammad PLD 2007 SC 302, Bashir Ahmed 2011 SCMR 1062, and Allah Ditta 2013 SCMR 866), you MUST declare the Supreme Court rule as the controlling law.
   - Explicitly highlight when a procedural defect (such as withholding the informer who relayed knowledge of sale) results in the dismissal of a pre-emption suit.

0. STRICT DRAFTING & ANTI-LEAKAGE DIRECTIVE:
   CRITICAL: Do NOT output your internal thinking, validation checklists, or meta-commentary. Do NOT ask for permission to output the draft. If the user commands drafting or the intake context is complete, output the full, court-ready pleading immediately, beginning directly with the Court Heading.

1. LIMITATION ACT, 1908 (STRICT ENFORCEMENT & CODIFICATION):
   - Body of Limitation Act: The Limitation Act 1908 contains ONLY Sections 1 through 32. NEVER cite 'Section 38' or any section above 32.
   - Specific Performance of an Agreement to Sell: Governed EXCLUSIVELY by Article 113 of the Limitation Act, 1908.
     * LIMITATION IS THREE (3) YEARS. NEVER cite 12 years.
     * Period runs from: (a) the date fixed for performance, or (b) if no date is fixed, when plaintiff has notice that performance is refused.
   - Mesne Profits: Governed strictly by Article 109 of the Limitation Act, 1908.
     * LIMITATION IS THREE (3) YEARS. NEVER cite 12 years.
   - Right to Partition: Partition is a continuous, recurring right. It is NOT governed by a numbered section of the Limitation Act, but by the settled principle that joint ownership creates a recurring cause of action (PLD 2003 SC 410). No limitation period applies so long as property remains joint.

2. SPECIFIC RELIEF ACT, 1877, PUNJAB RENTED PREMISES ACT 2009 & PARTITION PROCEDURE:
   - Suit for Specific Performance of a contract/agreement to sell is filed under SECTION 12 (NEVER Sections 8 or 9).
   - Under Explanation to Section 12, the Court presumes breach of contract to transfer immovable property cannot be adequately relieved by money damages.
   - Suit for Declaration of title and possession is under Section 42; Injunctions are under Section 54/55.
   - Commercial & Residential Eviction in Punjab (PRPA 2009): Eviction of commercial or residential rented premises in Punjab (Lahore, Faisalabad, Rawalpindi, Multan) is governed EXCLUSIVELY by the Punjab Rented Premises Act 2009 (PRPA 2009). The proper forum is the Rent Tribunal / Special Judge Rent under Section 16/19 PRPA 2009. Recommending an ordinary civil suit under Section 9 CPC or Senior Civil Judge for tenancy eviction in Punjab is a fatal procedural error. Tentative rent order is governed by Section 13 PRPA 2009.
   - Urban Partition in Punjab (PPIPA 2012): Governed exclusively by the Punjab Partition of Immoveable Property Act, 2012. Section 12 governs interim mesne profits/rent deposit. Section 7 deals strictly with appearance/written statement procedure.
   - Small Urban Parcels (PPIPA 2012): When urban residential plots under 10 marlas have multiple co-sharers, highlight the internal pre-emptive auction under Section 9/10 PPIPA 2012, as metes-and-bounds division is generally rejected for destroying economic utility.
   - Rendition of Accounts: Governed by Order XX Rule 16 CPC (preliminary decree for accounts) and inherent civil jurisdiction under Section 9 CPC.

3. TERRITORIAL & HIGH COURT JURISDICTION:
   - Lahore / Rawalpindi / Multan / Faisalabad -> LAHORE HIGH COURT (Punjab).
   - Karachi / Sukkur / Hyderabad -> SINDH HIGH COURT.
   - Peshawar / Abbottabad -> PESHAWAR HIGH COURT.
   - Quetta -> HIGH COURT OF BALOCHISTAN.
   - NEVER suggest a High Court of another province (e.g., never cite Balochistan High Court for Lahore or Rawalpindi disputes).

4. EVIDENTIARY RULES, TAX & NOMENCLATURE:
   - Always cite the Qanun-e-Shahadat Order, 1984 (QSO 1984). Citing the "Indian Evidence Act", "Indian Income-tax Act", or "IPC" is strictly prohibited.
   - Income tax assessment/reassessment in Pakistan is governed exclusively by the Income Tax Ordinance, 2001 (ITO 2001) and Customs Act, 1969.
   - QSO 1984 is divided into ARTICLES, not "Sections".
   - Article 79 QSO 1984 requires proving financial and property contracts by calling at least two attesting witnesses.
   - Section 271 of CPC DOES NOT EXIST (CPC ends at Section 158). Decrees are executed under Order XXI CPC.

5. CROSS-JURISDICTION STATUTORY DISAMBIGUATION (INDIA/UK/US LEAKAGE PREVENTION):
   CRITICAL: You have been trained on far more Indian, UK, and US legal text than Pakistani. Pakistan and India share a British colonial legal heritage, so an act name or section NUMBER can be correct for Pakistan while the SUBSTANCE you attach to it is silently imported from India's post-1947 amendments, which diverged from Pakistan's. A correct-looking citation with wrong-country substance is worse than an obviously foreign one, because it will not be caught by simply banning the word "Indian". Before stating what any section/article DOES, actively check it against this table where applicable:
   - Section 148, Income Tax Ordinance 2001 (Pakistan) = advance tax collection on imports. It is NOT "reassessment"/"reopening of assessment" -- that is India's Income-tax Act 1961 meaning. In Pakistan, reassessment/amendment of assessment is Section 122 ITO 2001.
   - Section 489-F, Pakistan Penal Code = dishonestly issuing a cheque towards repayment of a loan or fulfilment of an obligation, which is dishonoured on presentation (see Section 6 below for its exact bail classification -- do NOT casually call it "bailable"). It is NOT forgery (PPC Sections 463-471) and is NOT the same offence as India's Negotiable Instruments Act 1881 Section 138 cheque-dishonour framework -- Pakistan has no equivalent standalone Negotiable Instruments Act offence for this; do not cite the Negotiable Instruments Act as authority for cheque dishonour in Pakistan.
   - Limitation Act, 1908 (Pakistan, still in force) -- NOT the Limitation Act 1963 (that is India's replacement Act with different Articles/periods). Never cite "Limitation Act 1963" for a Pakistani matter.
   - Specific Relief Act, 1877 (Pakistan, still in force) -- NOT the Specific Relief Act 1963 (India's replacement, with materially different provisions on specific performance being discretionary vs. presumed). Never cite "Specific Relief Act 1963" for a Pakistani matter.
   - Code of Criminal Procedure, 1898 (Pakistan, still in force, CrPC) -- NOT India's Code of Criminal Procedure 1973, which uses entirely different section numbers for the same concepts. Do NOT call pre-arrest bail "anticipatory bail under Section 438" -- that is India's 1973 Code terminology and numbering; Pakistan's equivalent is Section 498 CrPC 1898 pre-arrest bail.
   - Companies Act, 2017 (Pakistan, regulated by SECP) -- NOT India's Companies Act 2013. Different section numbering entirely.
   - National Accountability Ordinance, 1999 (NAB Ordinance, Pakistan) governs corruption/accountability matters -- NOT India's Prevention of Corruption Act 1988.
   - Financial Institutions (Recovery of Finances) Ordinance, 2001 (FIO 2001, Pakistan) governs bank/financial recovery suits -- NOT India's SARFAESI Act 2002 or DRT Act.
   - Muslim Family Laws Ordinance, 1961 (Pakistan) governs Muslim family matters including the Arbitration Council mechanism for divorce/reconciliation -- do not import Indian personal-law procedure or terminology.
   - Pakistan Penal Code (PPC) retains its own post-1947 amendments (e.g. 489-F was added specifically to the PPC) and has diverged from the Indian Penal Code (IPC) despite a shared origin -- never assume a section means the same thing in both simply because the numbering looks similar.
   - If you are not certain a section's substance is the Pakistani version and not a colonial-era counterpart's amended version, say so explicitly and flag it for verification rather than stating it with false confidence.

6. CRIMINAL PROCEDURE -- BAIL CLASSIFICATION (NON-BAILABLE vs. OUTSIDE PROHIBITORY CLAUSE):
   CRITICAL DISTINCTION: "Non-bailable" and "bail is discretionary/hard to get" are NOT the same thing under Pakistani law. Do not conflate them.
   - Section 489-F PPC (dishonestly issuing a cheque) is explicitly classified as cognizable, NON-BAILABLE, and compoundable (with permission of the Court) under Schedule II of the Code of Criminal Procedure, 1898. NEVER describe it as a "bailable offence" -- that is a serious, court-embarrassing statutory error. If it were truly bailable, the accused would be entitled to bail as of right at the police station under Section 496 CrPC, making a pre-arrest bail application under Section 498 CrPC unnecessary.
   - However, because its maximum punishment (3 years) is below the threshold in the prohibitory clause of Section 497(1) CrPC (which applies only to offences punishable with death, imprisonment for life, or imprisonment for 10 years or more), Section 489-F falls OUTSIDE that prohibitory clause. For non-prohibitory-clause offences, the Supreme Court has held that the grant of bail is the rule and refusal is the exception (Tariq Bashir v. The State, PLD 1995 SC 34).
   - The correct, precise formulation: "Section 489-F PPC is a non-bailable offence, but because it falls outside the prohibitory clause of Section 497(1) CrPC, bail is the rule rather than the exception under the Tariq Bashir doctrine." Never shortcut this to simply "bailable."
   - VERBATIM STATUTORY TEXT -- quote this exactly, do not paraphrase, when drafting grounds, FIR analysis, or charges referencing this section: "489-F. Dishonestly issuing a cheque.-- Whoever dishonestly issues a cheque towards repayment of a loan or fulfilment of an obligation which is dishonoured on presentation, shall be punishable with imprisonment which may extend to three years, or with fine, or with both, unless he can establish, for which the burden of proof shall rest on him, that he had made arrangements with his bank to ensure that the cheque would be honoured and that the bank was at fault in not honouring the cheque." In general, when a draft turns on the exact wording of an offence-defining or rights-defining provision, prefer quoting the precise statutory language you have been given over paraphrasing it in your own words -- a paraphrase that drifts from the exact statutory phrase (e.g. writing "as a security for a loan" instead of the statute's actual "fulfilment of an obligation") is exactly the kind of imprecision a sitting judge will notice and reject.

7. PRE-ARREST / ANTICIPATORY BAIL DRAFTING COMPLETENESS (PUNJAB):
   When drafting a pre-arrest bail application/petition for a Punjab court, the final document is incomplete, and will be rejected by the Registrar's office, unless it includes ALL of the following as separate components, not just a Certificate of Urgency:
   - The main Application/Petition body with grounds and prayer.
   - A standalone, separately-headed Supporting Affidavit sworn on oath by the applicant/petitioner, verifying the facts stated in the petition -- this is mandatory under the High Court Rules and Orders for pre-arrest bail petitions in Punjab and is commonly missed. Do not omit it.
   - A Certificate of Urgency, if urgent interim relief is sought.
   If you are not asked to produce the full set and the user only asked for "the application," proactively note in your answer that a Supporting Affidavit is also required and will need to be prepared/sworn, rather than silently omitting it.

8. PAKISTANI LAW REPORTER JOURNAL CITATION DIRECTIVE:
   ALWAYS format judgment citations using standard Pakistani law reporter journal style:
   - PLD YEAR Court Page (e.g. PLD 1995 Supreme Court 34)
   - SCMR YEAR Page (e.g. 2019 SCMR 984)
   - PCrLJ YEAR Page (e.g. 2008 PCrLJ 858)
   - CLC YEAR Page
   - MLD YEAR Page
   - YLR YEAR Page
   - CLD YEAR Page
   - PTD YEAR Page
   - PLC YEAR Page (PLC (CS) for Civil Service)
   - PLJ YEAR Page
   - NLR YEAR Page
   - GBLR YEAR Page
   - PTCL YEAR Page
   - ALD YEAR Page
   - SLR YEAR Page
   - ILR YEAR Page
   - SBLR YEAR Page
   ONLY if a judgment record does NOT contain one of these official journal citations in database metadata, fallback to docket/court format (e.g. Supreme Court — Civil Appeal No. 870 of 2012).

9. NARCOTICS CHAIN-OF-CUSTODY DIRECTIVE (CNSA 1997):
   In CNSA 1997 prosecutions, safe custody and safe transmission are mandatory links. Failure to examine the Moharrir (Malkhana in-charge) or the official who transmitted samples to the Chemical Examiner breaks the chain of custody. Under Ikramullah (2015 SCMR 1002) and Imam Bakhsh (2018 SCMR 2039), this break renders the Chemical Examiner's report inadmissible, entitling the accused to an acquittal even if the chemical report is positive.

10. FAMILY COURT & CIVIL MONEY DECREE EXECUTION / SECTION 58 CPC DIRECTIVE:
    In execution of Family Court and civil money decrees, civil imprisonment under Section 51 and Section 58 CPC / Section 13 Family Courts Act 1964 does NOT discharge or waive the decretal debt. Serving the period of detention only bars the judgment-debtor from being re-arrested for that same default under Section 58(2) CPC; the decree remains alive and enforceable against his property, salary, and assets. Do NOT cite Section 34 CPC (which deals with interest) or Article 109 Limitation Act.

11. HIGH COURT REPORTER VS. SUPREME COURT JURISDICTION DIRECTIVE:
   - Citations containing MLD, CLC, or PCrLJ are High Court decisions (Lahore, Sindh, Peshawar, Balochistan, or Islamabad High Court). Citations containing YLR primarily report High Court decisions, but also include Supreme Court decisions where indicated in official court metadata.
   - SCMR reports Supreme Court decisions exclusively; PLD reports both Supreme Court and High Court decisions depending on the forum designated in the citation (e.g., PLD SC vs. PLD Lah).
   - If a citation is MLD, CLC, PCrLJ, or a High Court YLR / PLD entry, NEVER describe or output 'Supreme Court of Pakistan' as the deciding forum. Adhere strictly to the verified court metadata of the source record.

12. BANK GUARANTEE & INJUNCTION DIRECTIVE (ORDER XXXIX CPC & AUTONOMY DOCTRINE):
   - Core Autonomy Doctrine: An unconditional bank guarantee is an autonomous contract independent of the underlying agreement. Breaches of the underlying contract (e.g., delayed site handover, design approvals, alleged wrongful termination) do NOT ground an interim injunction under Order XXXIX Rules 1 & 2 CPC (2021 SCMR 1446 / 2021 SCP 3209; PLD 2003 SC 191).
   - The Two Exclusive Exceptions:
     1. Fraud of an egregious nature known to the bank (vitiating the very foundation of the transaction, such as encashment demand when underlying obligation is fully satisfied to beneficiary's own knowledge).
     2. Irretrievable injustice / special equities (e.g., beneficiary is an insolvent entity or foreign entity with no assets within Pakistani court jurisdiction, precluding recovery by subsequent damages decree).
   - Forum Selection (Contractual Procurement):
     * Constitutional Writ Petitions under Article 199 DO NOT lie to enforce non-statutory commercial procurement contracts or restrain bank guarantee encashment (1998 SCMR 2268; 2021 SCMR 1271). Recommending Article 199 writ for commercial guarantee disputes is a fatal procedural error.
     * Proper Forum: 
       - Plenary Civil Suit before the Senior Civil Judge under Section 9 CPC, OR
       - Application under Section 41 read with Second Schedule of the Arbitration Act 1940 (or Section 11 Recognition & Enforcement Act 2011 if international) before the designated civil court having jurisdiction if contract contains an arbitration clause.
   - Civil Court Subject-Matter Jurisdiction: The Civil Court HAS Section 9 subject-matter jurisdiction over bank guarantee suits, but must refuse Order XXXIX interim injunctions on substantive legal grounds unless the strict fraud / irretrievable injustice exceptions are proven with unimpeachable evidence.

13. COMMERCIAL & BANKING LAW / FIO 2001 SECTION 10 DIRECTIVE:
    Under Section 10 of the Financial Institutions (Recovery of Finances) Ordinance 2001, compliance with subsections (3), (4), and (5) is mandatory. As held in Apollo Textile Mills (PLD 2012 SC 268) and Tri-Star Shipping (2015 SCMR 1060), failure to provide a specific statement of accounts or formulated dispute points is fatal. The Banking Court has no jurisdiction to grant conditional leave on deposit of security and must reject the leave application and pass a decree under Section 10(11).

14. CONSTITUTIONAL WRITS & FISCAL STATUTES (ARTICLE 199 & ITO 2001 DIRECTIVE):
    Under Article 199 of the Constitution of Pakistan, the presence of an adequate alternate statutory remedy (such as appeals under Section 127 Income Tax Ordinance 2001) generally bars the entertainment of a writ petition. As settled in Collector of Customs v. Sheikh Spinning Mills (1999 SCMR 1402) and Premier Systems (2022 SCMR 1978), allegations of procedural defect, ex-parte order, or lack of notice under Section 122(9) fall squarely within the remedial jurisdiction of the Commissioner (Appeals) and ATIR, unless the order is completely coram non judice or passed under an ultra vires law.

15. CORPORATE OPPRESSION & WINDING UP DIRECTIVE (SECTIONS 286 & 301 COMPANIES ACT 2017):
    Under the Companies Act 2017, winding up of a commercially solvent and running company under the 'just and equitable' clause (Section 301) is strictly a remedy of last resort. Where minority shareholders allege oppression, mismanagement, or deadlock under Section 286, the Company Bench must explore alternative corrective remedies (such as forensic audits, restructuring of boards, or ordering a share purchase at fair valuation). The Court will not order the corporate death of a solvent company where its substratum remains intact, in accordance with Haji Muhammad Ismail (PLD 2002 SC 510).

16. STATUTORY INTERPRETATION -- CONFLICT BETWEEN SPECIAL LAWS & COMPETING NON-OBSTANTE CLAUSES:
    - Where two special statutes both contain non-obstante clauses ("notwithstanding anything contained in any other law for the time being in force") and are in direct, irreconcilable conflict, the statute enacted LATER IN TIME generally prevails over the prior statute (leges posteriores priores contrarias abrogant), as settled by the 5-Judge Bench of the Supreme Court of Pakistan in Syed Mushahid Shah v. Federal Investigation Agency (2017 SCMR 1218).
    - This rule is not mechanical: the Court must examine the object, purpose, and policy of both enactments and ascertain legislative intent. Non-obstante clauses must be understood in context and set aside earlier provisions only to the extent of direct inconsistency.
    - Concurrent Jurisdiction Bar (Articles 4 & 25): Where parallel operation of two special laws would permit an entity or prosecution to pick and choose between a harsher forum/penalty (e.g. Offences in Respect of Banks Special Courts Ordinance 1984) and a more protective or specialized forum (e.g. Financial Institutions Recovery of Finances Ordinance 2001), concurrent operation is impermissible as it violates Articles 4 and 25 of the Constitution. The later enactment (FIO 2001) prevails exclusively.

17. STRICT QUOTATION MARK DISCIPLINE (ANTI-HALLUCINATION QUOTES):
    Never wrap synthesized summaries or explanations in quotation marks. Use quotation marks only when extracting verbatim text lines directly from the source judgment database.
    Write all analytical conclusions, conceptual restatements, and headnote digests in clean unquoted prose. Quotation marks ("..." or “...”) and markdown blockquotes (> ...) are reserved exclusively for verbatim excerpts directly sourced from judgments or statutory text.

18. LIS PENDENS (SECTION 52 TPA), FRAUDULENT TRANSFERS (SECTION 53 TPA) & EXECUTION MECHANICS:
    - Section 52 TPA (Lis Pendens) applies ONLY where a right to specific immovable property is directly and specifically in question in the suit. It does NOT apply to an ordinary money suit, recovery suit, or maintenance claim unless the plaint specifically seeks to create a charge on or attach that specific property.
    - Money/Maintenance Debtor Alienation: When a judgment-debtor fraudulently alienates general property to defeat or delay execution of a money or maintenance decree, the substantive governing remedy is SECTION 53 of the Transfer of Property Act 1882 (fraudulent transfer voidable at the option of any creditor defeated or delayed).
    - Nature of Lis Pendens Transfer: An alienation pendente lite under Section 52 TPA is NOT "void", "void ab initio", or "cancelled". The sale remains valid between transferor and transferee, but is legally subservient and subject to the decree in the pending suit.
    - Section 52 vs. Section 41 TPA: Section 52 lis pendens is an EXCEPTION to Section 41 (bona fide purchaser for value without notice). A transferee pendente lite is bound by the result of the litigation regardless of lack of notice or good faith. Never describe Section 41 as an exception to lis pendens.
    - Execution Attachment: Attachment of immovable property in execution of a decree is strictly governed by ORDER XXI RULE 54 CPC. Citing Order XXI Rule 96 (which deals with delivery of possession to an auction-purchaser of property in occupancy of a tenant) for attachment is a fatal procedural error.
    - Cancellation of Deeds: Cancellation of void or voidable written instruments/sale deeds is governed strictly by SECTION 39 of the Specific Relief Act 1877. Never cite Section 54 (which governs perpetual injunctions) for cancellation or setting aside a deed.
    - Scope of Section 47 CPC: Section 47 CPC applies strictly to questions arising between the parties to the suit or their representatives. A third-party transferee or stranger claiming independent title is NOT determined summarily under Section 47; their claim must be investigated under ORDER XXI RULE 58 CPC (objections to attachment) or adjudicated via a separate suit under Section 53 TPA / Order XXI Rule 103 CPC.
    - Family Courts Act 1964 Execution (Section 17 CPC Bar): Under Section 17 of the Family Courts Act 1964, the CPC is expressly EXCLUDED from family proceedings (except Sections 10 and 11). Decrees of Family Courts (including maintenance and dower) execute under SECTION 13 of the Family Courts Act 1964 and Rule 22 of the West Pakistan Family Courts Rules 1965 (as arrears of land revenue or under the special civil court powers granted under Section 13(4)). Blanket application of the CPC without citing Section 13 and Section 17 is a fatal statutory error.

19. STRICT HOLDING VS. ADVOCATE ANALOGY SEPARATION DIRECTIVE:
    - In your analysis under "Cases Discussed" or case summaries:
      * The "Holding of the Court" must state ONLY what the judges actually held, ruled, and decided on the facts of that case.
      * NEVER invent, interpolate, or attribute non-existent ratios, presumptions, or tests (e.g. inventing a "four-part test" or "presumption of fraud on transfers to close relatives after a maintenance suit") to the Supreme Court or High Courts if not in the judgment text.
      * NEVER claim an authority is "directly governing" when it was decided under a completely different statute (e.g. do not cite a Contract Act attorney/principal case as "directly governing" execution of a family maintenance decree).
      * If you apply a case by analogy, you MUST cordone it off under a distinct sub-heading: "### Application by Analogy / Commentary" and explicitly disclose that the cited authority was decided on different statutory facts.
    - "Cases Discussed" counter and section must contain ONLY actual judicial precedents (citations to superior court judgments like SCMR, PLD, CLC), NEVER statutory section cards (like Section 42 SRA or Section 52 TPA).

20. MANDATORY GAP & NEGATIVE FINDING DISCLOSURE (NO HALLUCINATING UNLOCATED LEGAL STANDARDS):
    - If a user query asks about a specific numerical threshold (e.g. a "50% pre-deposit"), doctrine, or question (e.g. reserve price publication standards under Section 19 FIO 2001) and NO retrieved authority or statute in the context supports that premise:
      * You are STRICTLY FORBIDDEN from assuming, extrapolating, or pretending the premise is true.
      * You are STRICTLY FORBIDDEN from asserting that an unverified requirement "has survived constitutional challenge" or "is settled law" without a source directly in the retrieved context.
      * You MUST explicitly state in your Executive Summary and under a dedicated sub-heading: "### Issues Not Supported by Retrieved Authorities":
        - State clearly that no statutory provision or precedent was located in the verified database or court portals establishing that requirement.
        - Identify the actual verified statutory provision (e.g., the statutory deposit requirement under the second proviso to Order XXI Rule 90 CPC is strictly 20% of the sale proceeds, not 50%).
        - Advise the advocate that the 50% figure appears to be a false premise or an unverified ad-hoc condition from a lower court order.
"""


ROMAN_NUMERAL_MAP = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18,
    "xix": 19, "xx": 20, "xxi": 21, "xxii": 22, "xxiii": 23, "xxiv": 24, "xxv": 25, "xxvi": 26,
    "xxvii": 27, "xxviii": 28, "xxix": 29, "xxx": 30, "xxxix": 39, "xl": 40, "xli": 41
}

def normalize_statute_citation(cit: str) -> str:
    """
    Normalizes statutory citations across formatting conventions:
    'Order XXI Rule 66' <-> 'O.XXI, R.66' <-> 'Order 21, Rule 66' <-> 'O.21, R.66'
    'Section 19' <-> 'Sec. 19' <-> 'S. 19' <-> 's. 19'
    'Article 199' <-> 'Art. 199'
    """
    if not cit or not isinstance(cit, str):
        return ""
    c = cit.lower().strip()
    c = re.sub(r'[,;.]', ' ', c)
    c = re.sub(r'\s+', ' ', c).strip()

    def _sub_order(m):
        raw_val = m.group(1).lower().strip()
        num = ROMAN_NUMERAL_MAP.get(raw_val, raw_val)
        return f"order {num}"

    c = re.sub(r'\b(?:order|ord|o)\s+([ivxlcdm\d]+)', _sub_order, c)
    c = re.sub(r'\b(?:rule|r)\s+(\d+[a-z]?)', r'rule \1', c)
    c = re.sub(r'\b(?:section|sec|s)\s+(\d+[a-z]?)', r'section \1', c)
    c = re.sub(r'\b(?:article|art)\s+(\d+[a-z]?)', r'article \1', c)
    return c


def is_statute_in_source(statute_phrase: str, source_text: str) -> bool:
    """
    Checks if a normalized statute citation appears in a source text.
    """
    if not statute_phrase or not source_text:
        return False
    norm_phrase = normalize_statute_citation(statute_phrase)
    norm_source = normalize_statute_citation(source_text)
    if norm_phrase in norm_source:
        return True

    tokens = norm_phrase.split()
    if len(tokens) >= 4 and tokens[0] == "order" and tokens[2] == "rule":
        ord_part = f"order {tokens[1]}"
        rule_part = f"rule {tokens[3]}"
        return ord_part in norm_source and rule_part in norm_source
    if len(tokens) >= 2 and tokens[0] in ("section", "article"):
        sec_part = f"{tokens[0]} {tokens[1]}"
        return sec_part in norm_source

    return False


def is_compiled_headnote(text: str) -> bool:
    """
    Detects whether a precedent text is an editorial compiled headnote digest (e.g., from PLD/SCMR/CLD/YLR)
    rather than an actual verbatim judicial order or judgment text.
    
    Compiled headnotes exhibit:
    - Multiple catchword separator dashes ('----' or '---')
    - Editorial statute catchwords ('Civil Procedure Code (V of 1908)---', 'O. XXI, R. 90---', 'Ss. 15 & 19---')
    - Repeated editorial 'Held:' / 'Held, that' summaries
    - Volume/page editorial markers ('[p. 1087] A', '[pp. 1220] B')
    - Absence of authentic judicial opening preambles ('ORDER', 'JUDGMENT', 'Heard learned counsel', etc.)
    """
    if not text or not isinstance(text, str):
        return False
    t_clean = text.strip()
    if len(t_clean) < 30:
        return False

    has_dash_separators = len(re.findall(r'-{3,}', t_clean)) >= 2
    has_catchword_headers = bool(re.search(r'(?:[A-Z][A-Za-z\s\(\)]+\([A-Za-z\d\s]+\)---|\bO\.\s*[IVXLCDM\d]+[,\s]+R\.\s*\d+---|\bSs?\.\s*\d+---)', t_clean))
    has_repeated_held = len(re.findall(r'\bHeld\s*[:,]', t_clean, re.IGNORECASE)) >= 2
    has_editorial_page_pins = bool(re.search(r'\[pp?\.?\s*\d+[^\]]*\]\s*[A-Z]', t_clean))

    judicial_hallmarks = [
        r'^\s*(?:ORDER|JUDGMENT)\b',
        r'\b(?:heard\s+(?:the\s+)?learned\s+counsel|through\s+this\s+(?:petition|appeal|suit))\b',
        r'\b(?:this\s+(?:civil\s+)?(?:petition|appeal|application)\s+is\s+directed\s+against)\b',
        r'\b(?:leave\s+to\s+appeal\s+was\s+granted)\b',
        r'\b(?:the\s+impugned\s+(?:judgment|order)\s+dated)\b',
        r'\b(?:brief\s+facts\s+(?:of\s+the\s+case|are\s+that))\b',
        r'\b(?:advocate\s+for\s+(?:the\s+)?petitioner|advocate\s+supreme\s+court)\b',
        r'\b(?:by\s+this\s+(?:common\s+)?order)\b',
        r'\b(?:we\s+have\s+heard|perused\s+the\s+record)\b',
    ]
    t_first_500 = t_clean[:500]
    has_judicial_hallmark = any(re.search(pat, t_first_500, re.IGNORECASE | re.MULTILINE) for pat in judicial_hallmarks)

    if (has_dash_separators or has_catchword_headers or has_repeated_held or has_editorial_page_pins) and not has_judicial_hallmark:
        return True

    if (len(re.findall(r'-{3,}', t_clean)) >= 3) and (has_repeated_held or has_editorial_page_pins):
        return True

    return False


def lint_legal_output(draft_text: str, query_context: str = "", context_chunks: Optional[List[Any]] = None) -> List[str]:
    """
    Deterministically scans generated legal drafts for severe statutory hallucinations,
    limitation misstatements, foreign acts, phantom CPC sections, and territorial mismatches.
    """
    errors = []
    text_lower = draft_text.lower()
    query_lower = query_context.lower()

    # Build comprehensive context string from query_context and context_chunks
    context_parts = [query_context or ""]
    if context_chunks:
        for c in context_chunks:
            if isinstance(c, dict):
                meta = c.get("metadata", {}) if isinstance(c.get("metadata"), dict) else {}
                txt = c.get("full_judgment_body") or c.get("text") or c.get("preview") or meta.get("text") or meta.get("full_text") or ""
                cit = c.get("citation") or c.get("neutral_citation") or meta.get("citation") or meta.get("neutral_citation") or ""
                title = c.get("case_name") or c.get("title") or meta.get("title") or meta.get("case_title") or ""
                context_parts.extend([str(cit), str(title), str(txt)])
            else:
                context_parts.append(str(c))
    full_context_text = " ".join(context_parts)

    # Rule 1: Specific performance limitation checks
    if any(k in query_lower or k in text_lower for k in ["specific performance", "agreement to sell", "sale agreement"]):
        if re.search(r'\b12\s*years?\b', text_lower) and ("specific performance" in text_lower or "agreement to sell" in text_lower):
            errors.append("Citing 12 years limitation for Specific Performance (Article 113 strictly dictates 3 years).")
        if re.search(r'article\s*109\b', text_lower) and ("specific performance" in text_lower or "agreement to sell" in text_lower):
            errors.append("Citing Article 109 for Specific Performance (Article 109 applies only to mesne profits; specific performance is Article 113).")

    # Rule 2: Foreign statutes & phantom CPC / Limitation Act / Banking sections
    if re.search(r'section\s*(3[3-9]|[4-9]\d|\d{3,})\s*(of\s*)?(the\s*)?limitation act', text_lower):
        errors.append("Citing phantom section of Limitation Act 1908 (Limitation Act body ends at Section 32; Articles 1-149 belong to the First Schedule).")
    if re.search(r'\b(banking regulation act)\b', text_lower):
        errors.append("Citing foreign 'Banking Regulation Act' (Pakistani banks are governed under Banking Companies Ordinance 1962 - BCO 1962).")
    if re.search(r'\bindian evidence act\b', text_lower):
        errors.append("Citing 'Indian Evidence Act' instead of Qanun-e-Shahadat Order, 1984 (QSO 1984).")
    if re.search(r'\b(indian income-?\s*tax act|income tax act 1961)\b', text_lower):
        errors.append("Citing foreign 'Indian Income-tax Act' instead of Income Tax Ordinance 2001 (ITO 2001).")
    if re.search(r'\b(indian penal code|ipc)\b', text_lower):
        errors.append("Citing 'IPC' / 'Indian Penal Code' instead of Pakistan Penal Code (PPC).")
    if re.search(r'\bsection\s*271\s*cpc\b', text_lower):
        errors.append("Citing non-existent 'Section 271 CPC' (CPC ends at Section 158; decrees execute under Order XXI CPC).")

    # Rule 3: Article 199 Writ Damages, Commercial Guarantee Writs & Procedural hygiene
    if ("bank guarantee" in text_lower or "performance guarantee" in text_lower or "encashment" in text_lower) and ("article 199" in text_lower or "writ petition" in text_lower):
        errors.append("Recommending Article 199 Writ Petition for commercial bank guarantee encashment disputes (Article 199 writ does not lie for non-statutory commercial contracts under 1998 SCMR 2268; proper forum is Section 9 CPC civil suit or Section 41 Arbitration Act 1940).")
    if ("article 199" in text_lower or "writ petition" in text_lower) and re.search(r'\b(award|grant|decree)\s+damages\b', text_lower):
        errors.append("Praying for unliquidated commercial/tortious damages in an Article 199 Writ Petition (damages cannot be awarded in writ jurisdiction under PLD 2005 SC 530; requires an ordinary civil suit).")

    # Rule 3: Specific Relief Act / Partition / SRPO Eviction / FIO 2001 Civil Court Bar misclassifications
    if ("financial institution" in text_lower or "fio 2001" in text_lower or "mortgage auction" in text_lower or "section 15" in text_lower) and re.search(r'\b(civil court|senior civil judge)\b', text_lower) and ("order 39" in text_lower or "civil suit" in text_lower):
        errors.append("Recommending an ordinary civil suit / Order XXXIX CPC before Civil Judge for Banking Mortgage/FIO 2001 disputes (Section 7 FIO 2001 expressly bars Civil Court jurisdiction; remedy lies before Banking Court or Article 199 High Court Writ).")
    if ("eviction" in query_lower or "tenancy" in query_lower or "rented premises" in query_lower) and any(city in query_lower for city in ["lahore", "faisalabad", "rawalpindi", "multan", "punjab"]) and re.search(r'\b(senior civil judge|civil court|section 9 cpc)\b', text_lower) and "rent tribunal" not in text_lower:
        errors.append("Recommending ordinary Civil Court / Section 9 CPC for Punjab commercial/residential tenancy eviction (eviction in Punjab is governed exclusively by the Punjab Rented Premises Act 2009 - PRPA 2009 before the Rent Tribunal / Special Judge Rent).")
    if re.search(r'section\s*[89]\s*(of\s*)?(the\s*)?specific relief act', text_lower) and "partition" in text_lower:
        errors.append("Citing Sections 8 or 9 of SRA 1877 for partition (urban partition in Punjab is governed by PPIPA 2012).")
    if re.search(r'section\s*7\s*(of\s*)?(the\s*)?(punjab partition|ppipa)', text_lower) and ("interim" in text_lower or "mesne profit" in text_lower or "rent deposit" in text_lower):
        errors.append("Citing Section 7 PPIPA 2012 for interim rent deposit (Section 12 PPIPA 2012 governs interim mesne profits/rent deposit).")
    if re.search(r'section\s*13\s*(of\s*)?(the\s*)?(sindh rented premises|srpo)', text_lower) and ("eviction" in text_lower or "ejectment" in text_lower or "default" in text_lower):
        errors.append("Citing Section 13 SRPO 1979 for eviction (Section 15 SRPO 1979 governs eviction; Section 13 is for tenant repairs).")

    # Rule 4: Provincial forum mismatches
    punjab_cities = ["lahore", "rawalpindi", "multan", "faisalabad", "dha lahore", "dha phase"]
    has_punjab_query = any(city in query_lower for city in punjab_cities)
    if has_punjab_query:
        if ("high court of balochistan" in text_lower or "balochistan high court" in text_lower) and not any(k in query_lower for k in ["balochistan", "quetta"]):
            errors.append("Territorial Mismatch: Recommending High Court of Balochistan for a Punjab/Lahore/Rawalpindi dispute.")
        if ("peshawar high court" in text_lower) and not any(k in query_lower for k in ["peshawar", "khyber", "kp", "kpk"]):
            errors.append("Territorial Mismatch: Recommending Peshawar High Court for a Punjab dispute.")

    # Rule 5: Cross-jurisdiction SEMANTIC leakage (India/UK/US substance silently attached to a
    # correctly-named Pakistani act/section). These are harder than Rule 2's literal foreign-act-name
    # checks: the act name is right, but the meaning attached to it has been imported from another
    # jurisdiction's diverged version of a shared colonial-era statute.
    if re.search(r'\bsection\s*148\b', text_lower) and re.search(r'\b(income tax ordinance|ito\s*2001)\b', text_lower) and re.search(r'\b(reassess|reopen)', text_lower):
        errors.append("Describing Section 148 ITO 2001 as 'reassessment/reopening' -- that is India's Income-tax Act meaning. Pakistan's Section 148 ITO 2001 is advance tax on imports; reassessment in Pakistan is Section 122 ITO 2001.")
    if re.search(r'\b489-?f\b', text_lower) and re.search(r'\b(forgery|cheating\s+and\s+dishonestly)\b', text_lower) and "cheque" not in text_lower:
        errors.append("Describing Section 489-F PPC as forgery/cheating without reference to cheque dishonour -- 489-F is specifically the dishonest-cheque-issuance offence, not general forgery (PPC Sections 463-471).")
    if re.search(r'\bnegotiable instruments act\b', text_lower) and any(k in text_lower for k in ["cheque", "dishonour", "dishonor", "bounce"]):
        errors.append("Citing the Negotiable Instruments Act for cheque dishonour -- Pakistan has no standalone Negotiable Instruments Act offence for this; the governing provision is Section 489-F PPC.")
    if re.search(r'\blimitation act,?\s*1963\b', text_lower):
        errors.append("Citing 'Limitation Act 1963' -- Pakistan retains the Limitation Act 1908; 1963 is India's replacement Act with different Articles/periods.")
    if re.search(r'\bspecific relief act,?\s*1963\b', text_lower):
        errors.append("Citing 'Specific Relief Act 1963' -- Pakistan retains the Specific Relief Act 1877; 1963 is India's replacement Act with materially different provisions.")
    if re.search(r'\bcode of criminal procedure,?\s*1973\b', text_lower) or re.search(r'\bcrpc,?\s*1973\b', text_lower):
        errors.append("Citing 'CrPC 1973' -- Pakistan retains the Code of Criminal Procedure 1898; 1973 is India's replacement Code with different section numbers for the same concepts.")
    if re.search(r'\banticipatory bail\b', text_lower) and re.search(r'\bsection\s*438\b', text_lower):
        errors.append("Citing 'anticipatory bail under Section 438' -- that is India's CrPC 1973 terminology/numbering. Pakistan's equivalent is pre-arrest bail under Section 498 CrPC 1898.")
    if re.search(r'\bcompanies act,?\s*2013\b', text_lower):
        errors.append("Citing 'Companies Act 2013' -- Pakistan's company law is the Companies Act 2017 (SECP-regulated); 2013 is India's Companies Act.")
    if re.search(r'\bprevention of corruption act\b', text_lower):
        errors.append("Citing 'Prevention of Corruption Act' -- Pakistan's accountability/corruption law is the National Accountability Ordinance 1999 (NAB Ordinance), not India's Prevention of Corruption Act 1988.")
    if re.search(r'\bsarfaesi\b', text_lower):
        errors.append("Citing 'SARFAESI' -- that is India's recovery law. Pakistan's equivalent for bank/financial institution recovery is the Financial Institutions (Recovery of Finances) Ordinance 2001 (FIO 2001).")
    if re.search(r'\bevidence act,?\s*1872\b', text_lower) and "indian" not in text_lower:
        errors.append("Citing 'Evidence Act 1872' -- Pakistan replaced this with the Qanun-e-Shahadat Order 1984 (QSO 1984); do not cite the 1872 Evidence Act framework even without the word 'Indian'.")

    # Rule 6: Section 489-F PPC bail classification -- non-bailable is a matter of statutory fact
    # (Schedule II CrPC 1898), independent of the "bail is the rule" Tariq Bashir doctrine that
    # applies BECAUSE it's outside the prohibitory clause. Conflating the two is a serious,
    # court-embarrassing error that keeps recurring, so it gets its own explicit check.
    if re.search(r'489-?f', text_lower):
        if re.search(r'\bis\s+a\s+bailable\s+offen', text_lower) or re.search(r'489-?f\s+ppc\s+is\s+bailable\b', text_lower):
            errors.append("Describing Section 489-F PPC as a 'bailable offence' -- it is NON-BAILABLE under Schedule II CrPC 1898. It falls outside the Section 497(1) prohibitory clause (max punishment 3 years), so bail is the rule rather than the exception under Tariq Bashir v. The State (PLD 1995 SC 34) -- but it is still, as a matter of statutory classification, non-bailable. Never shortcut this to 'bailable'.")
        elif re.search(r'\bbailable\b', text_lower) and "non-bailable" not in text_lower and "not bailable" not in text_lower:
            errors.append("Discussing Section 489-F PPC and the word 'bailable' without ever stating it is NON-bailable -- confirm the draft explicitly classifies it as non-bailable (Schedule II CrPC 1898) even while explaining that bail is the rule under Tariq Bashir since it falls outside the Section 497(1) prohibitory clause.")

    # Rule 7: Pre-arrest bail drafting completeness (Punjab) -- a full court-ready application
    # needs a standalone sworn Supporting Affidavit, not just a Certificate of Urgency.
    is_full_draft = bool(re.search(r'\bin\s+the\s+court\s+of\b', text_lower)) and len(draft_text) > 800
    if is_full_draft and re.search(r'\bpre-?arrest\s+bail\b', text_lower) and "affidavit" not in text_lower:
        errors.append("Drafting a Punjab pre-arrest bail application without a standalone, separately-headed Supporting Affidavit sworn on oath -- this is mandatory under the High Court Rules and Orders and is commonly missed; a Certificate of Urgency alone is not sufficient.")

    # Rule 8: High Court Reporter vs Supreme Court hallucination check
    hc_reporters_pattern = r'\b((?:19|20)\d{2}\s+(?:YLR|MLD|CLC|PCrLJ|PCRLJ)\s+\d+)\b'
    hc_matches = re.finditer(hc_reporters_pattern, draft_text, re.IGNORECASE)
    for m in hc_matches:
        cit_str = m.group(0)
        start_w = max(0, m.start() - 120)
        end_w = min(len(draft_text), m.end() + 120)
        snippet = draft_text[start_w:end_w].lower()
        if "supreme court" in snippet and "scmr" not in snippet and "pld sc" not in snippet and "pld supreme court" not in snippet:
            errors.append(f"Citations containing YLR, MLD, CLC, or PCrLJ ('{cit_str}') are High Court decisions -- do not attribute them to the Supreme Court of Pakistan.")

    # Rule 9: Temporal / statutory anachronism check (pre-2009 cases attributed to PRPA 2009)
    if "punjab rented premises act" in text_lower or "prpa" in text_lower:
        pre_2009_citations = re.findall(r"\b(19\d\d|200[0-8])\s+(YLR|SCMR|PLD|MLD|CLC|PCRLJ|PCRLJ)\s+(\d+)\b", draft_text, re.IGNORECASE)
        for year, journal, page in pre_2009_citations:
            if f"{year} {journal} {page}".lower() in text_lower and ("under the punjab rented premises act" in text_lower or "interpreting the 2009 act" in text_lower):
                errors.append(f"Anachronistic statutory attribution: {year} {journal} {page} predates the Punjab Rented Premises Act 2009.")

    # Rule 10: Bare / ungrounded additional authorities list check
    if "additional relevant authorities" in text_lower or "additional authorities" in text_lower:
        parts = re.split(r'additional\s+(?:relevant\s+)?authorities', draft_text, flags=re.IGNORECASE)
        if len(parts) > 1:
            additional_section = parts[-1]
            bare_citations = re.findall(r"\b((?:19|20)\d{2}\s+(?:YLR|SCMR|PLD|MLD|CLC|PCRLJ|PCRLJ)\s+\d+)\b", additional_section, re.IGNORECASE)
            
            chunk_citations = set()
            if context_chunks:
                for c in context_chunks:
                    meta = c.get("metadata", {}) if isinstance(c, dict) else getattr(c, "metadata", {}) or {}
                    cit = str(meta.get("citation") or meta.get("neutral_citation") or "").replace(" ", "").upper()
                    if cit:
                        chunk_citations.add(cit)

            for raw_cit in bare_citations:
                clean_c = raw_cit.replace(" ", "").upper()
                if chunk_citations and clean_c not in chunk_citations:
                    errors.append(f"Ungrounded authority detected in additional citations: {raw_cit}")

    # Rule 11: Khula / MFLO 1961 statutory fidelity & consent hallucination
    if any(k in text_lower or k in query_lower for k in ["khula", "zar-i-khula", "dissolution of marriage"]):
        if re.search(r'section\s*2\s*\([a-z0-9ivx]+\)\s*(of\s*)?(the\s*)?mflo', text_lower) or "section 2(viii)" in text_lower or "2(viii) mflo" in text_lower:
            errors.append("Citing phantom Section 2(viii) MFLO 1961 (Section 2 contains only definitions: Chairman, Council, Prescribed; it has no subsection viii).")
        if re.search(r'khula\s+(?:is\s+a\s+contractual\s+dissolution|requires\s+(?:the\s+)?husband(?:\'s)?\s+consent)', text_lower) or "requires mutual agreement or, in the absence of agreement, the husband's consent" in text_lower:
            errors.append("Holding that Khula requires husband's consent (Fatal error: Under Khurshid Bibi v. Muhammad Amin PLD 1967 SC 97 and Family Courts Act 1964 Section 10, the wife has an independent right to Khula and husband's consent is NOT required).")

    # Rule 12: Pre-emption / Informer non-production stare decisis (PLD 2007 SC 302 / 2011 SCMR 1062)
    if any(k in text_lower or k in query_lower for k in ["pre-emption", "preemption", "talb-i-muwathibat", "informer"]):
        if ("informer" in text_lower or "informant" in text_lower) and re.search(r'(?:omission|withholding|non-production|failure\s+to\s+produce)\s+(?:of\s+)?(?:the\s+)?informer\s+is\s+(?:not\s+fatal|curable|not\s+a\s+fatal\s+defect)', text_lower):
            errors.append("Erroneously holding that non-production of the informer is not fatal (Controlling law under Supreme Court PLD 2007 SC 302 and 2011 SCMR 1062: withholding the informer from the witness box is a fatal defect resulting in dismissal of the pre-emption suit).")

    # Rule 13: Phase 2 Statutory Citation Validation & Hybrid Hallucination Interception
    try:
        from core.statutory_validator import validate_citations_in_text
        stat_res = validate_citations_in_text(draft_text)
        for h in stat_res.get("hybrids", []):
            errors.append(f"Hybrid Statutory Hallucination: '{h['raw_citation']}' conflates a substantive Section with a procedural Order/Rule in the Code of Civil Procedure, 1908 (these do not exist as a single combined provision).")
        for u in stat_res.get("unverified", []):
            errors.append(f"Unverified Statutory Citation: '{u['raw_citation']}' could not be verified against official bare-act lookup tables.")
    except Exception:
        pass


    # Rule 13: CNSA 1997 narcotics chain of custody / safe transmission (Ikramullah / Imam Bakhsh)
    if any(k in text_lower or k in query_lower for k in ["cnsa", "narcotic", "charas", "heroin", "opium", "chain of custody", "malkhana", "chemical examiner"]):
        if ("chain of custody" in text_lower or "moharrir" in text_lower or "malkhana" in text_lower or "chemical examiner" in text_lower) and re.search(r'(?:failure\s+to\s+examine|non-production\s+of)\s+(?:the\s+)?(?:moharrir|carrier|official|constable)\s+is\s+(?:not\s+fatal|curable|a\s+mere\s+irregularity)', text_lower):
            errors.append("Erroneously stating that failure to examine the Moharrir or carrier official in CNSA prosecutions is not fatal (Controlling law under Ikramullah 2015 SCMR 1002, Imam Bakhsh 2018 SCMR 2039, and Abdul Ghani 2019 SCMR 608: failure to examine the Moharrir or transmitting official breaks the chain of custody, rendering the chemical examiner's report inadmissible and entitling the accused to acquittal).")

    # Rule 14: Family Court & civil money decree execution / Section 58 CPC civil imprisonment
    if any(k in text_lower or k in query_lower for k in ["section 58", "section 51", "civil imprisonment", "civil prison", "arrest and detention", "maintenance decree", "execution of decree", "judgment debtor", "decretal amount", "family court"]):
        if ("civil imprisonment" in text_lower or "detention" in text_lower or "civil prison" in text_lower) and re.search(r'(?:discharges?|waives?|satisfies?|extinguishes?)\s+(?:the\s+)?(?:decretal\s+)?(?:debt|amount|decree|liability)', text_lower):
            errors.append("Erroneously holding that civil imprisonment discharges or satisfies the decretal debt (Controlling law under Section 58(2) CPC and Section 13 Family Courts Act 1964: release from civil prison does not discharge the debt; it only bars re-arrest for the same default, leaving the decree enforceable against property and assets).")
        if re.search(r'section\s*34\s*cpc\b', text_lower) and any(kw in text_lower for kw in ["execution", "maintenance", "family court", "arrest", "civil prison"]):
            errors.append("Citing Section 34 CPC in decree execution/maintenance (Section 34 CPC deals with interest on commercial/civil decrees, not execution or maintenance debt).")
        if re.search(r'article\s*109\b', text_lower) and any(kw in text_lower for kw in ["execution", "maintenance", "family court", "arrest", "civil prison"]):
            errors.append("Citing Article 109 Limitation Act in decree execution/maintenance (Article 109 deals strictly with profits of immovable property/mesne profits; execution of decrees is governed by Article 181/182 Limitation Act / Section 48 CPC).")

    # Rule 15: FIO 2001 Section 10 Leave to Defend (Apollo Textile Mills / Tri-Star Shipping)
    if any(k in text_lower or k in query_lower for k in ["fio 2001", "financial institutions (recovery", "section 10", "leave to defend", "banking court", "recovery of finances"]):
        if ("section 10" in text_lower or "leave to defend" in text_lower or "banking court" in text_lower) and re.search(r'(?:subsections?\s*\(?(?:3|4|5)\)?\s*(?:is|are)\s*(?:directory|not\s+mandatory|curable|discretionary)|grant(?:ed|ing)?\s+conditional\s+leave\s+(?:on|upon)\s+deposit\s+of\s+security\s+(?:despite|notwithstanding)\s+(?:non-compliance|failure\s+to\s+comply))', text_lower):
            errors.append("Erroneously stating that Section 10(3)-(5) FIO 2001 requirements are directory or that the Banking Court has jurisdiction to grant conditional leave despite non-compliance (Controlling law under Apollo Textile Mills PLD 2012 SC 268 and Tri-Star Shipping 2015 SCMR 1060: compliance with Section 10(3)-(5) is strictly mandatory; failure to provide an itemized statement of accounts or formulated dispute points is fatal, and the Banking Court has no jurisdiction to grant conditional leave on deposit of security and must reject the leave application and pass a decree under Section 10(11)).")

    # Rule 16: Tax Appellate Hierarchy & Article 199 Writ Bar (Collector of Customs 1999 SCMR 1402 / Premier Systems 2022 SCMR 1978)
    if any(k in text_lower or k in query_lower for k in ["income tax", "ito 2001", "customs", "tax assessment", "section 122", "section 127", "commissioner inland revenue", "commissioner (appeals)", "atir", "sales tax"]):
        if ("article 199" in text_lower or "writ petition" in text_lower or "high court" in text_lower) and any(k in text_lower for k in ["natural justice", "notice", "122(9)", "ex-parte", "audi alteram"]):
            if re.search(r'(?:natural justice|lack of notice|122\(9\)|ex-parte|audi alteram partem).*(?:automatically\s+(?:bypasses|dispenses with|overrides|allows)|directly\s+(?:maintainable|entitles?|approache?s?)\s+(?:a\s+)?(?:writ|article 199)|writ\s+lies?\s+(?:directly\s+)?without\s+(?:exhausting|filing|availing)\s+(?:an?\s+)?(?:appeal|statutory\s+remedy|section 127)|exempt\s+from\s+(?:exhausting|availing)\s+(?:the\s+)?(?:statutory\s+remedy|appeal))', text_lower):
                errors.append("Erroneously asserting that natural justice defects, lack of Section 122(9) notice, or ex-parte tax assessment automatically bypass the statutory tax appellate hierarchy under Section 127 ITO 2001 (Controlling law under Collector of Customs v. Sheikh Spinning Mills 1999 SCMR 1402, Hamdard Dawakhana PLD 1992 SC 847, and Premier Systems 2022 SCMR 1978: statutory appeal under Section 127 before Commissioner Appeals and ATIR is an adequate alternate remedy under Article 199; procedural defects and natural justice grievances fall squarely within the appellate hierarchy's competence and cannot bypass statutory remedies unless the action is completely coram non judice or passed under an ultra vires law).")

    # Rule 17: Corporate Oppression & Just and Equitable Winding Up (Haji Muhammad Ismail PLD 2002 SC 510 / Sections 286 & 301 Companies Act 2017)
    if any(k in text_lower or k in query_lower for k in ["companies act", "company law", "winding up", "section 286", "section 301", "section 290", "oppression", "mismanagement", "minority shareholder", "just and equitable"]):
        if ("winding up" in text_lower or "corporate death" in text_lower or "section 301" in text_lower) and any(k in text_lower for k in ["solvent", "running company", "substratum intact", "oppression", "deadlock"]):
            if re.search(r'(?:winding up|corporate death).*(?:is\s+(?:the\s+)?(?:primary|first|routine|mandatory)\s+remedy|must\s+be\s+(?:ordered|granted)\s+(?:upon|for|on\s+grounds\s+of)\s+(?:minority\s+oppression|deadlock|mismanagement)|cannot\s+explore\s+alternative\s+remedies)', text_lower):
                errors.append("Erroneously asserting that winding up is the primary or mandatory remedy for corporate oppression/deadlock in a solvent company (Controlling law under Haji Muhammad Ismail PLD 2002 SC 510, 2017 CLD 847, and Section 286/301 Companies Act 2017: winding up of a commercially solvent and running company under the just and equitable clause is strictly a remedy of last resort; the Company Bench must explore alternative corrective remedies under Section 286 such as forensic audits, board restructuring, or ordering share buy-outs at fair valuation).")

    # Rule 18: Conflicting special laws with competing non-obstante clauses (Syed Mushahid Shah 2017 SCMR 1218)
    if any(k in query_lower for k in ["non-obstante", "non obstante", "non onstante", "non instante", "two special laws", "conflict between two special laws", "which would prevail", "which will prevail"]):
        if re.search(r'\bearlier\s+(?:special\s+)?(?:law|statute|enactment)\s+(?:shall\s+|will\s+|automatically\s+)?prevails?\b', text_lower) and not any(k in text_lower for k in ["mushahid shah", "2017 scmr 1218", "leges posteriores"]):
            errors.append("Erroneously stating that an earlier special law automatically prevails over a subsequent special law when both have non-obstante clauses (Controlling law under Syed Mushahid Shah v. FIA 2017 SCMR 1218: the statute enacted later in time generally prevails under leges posteriores priores contrarias abrogant, subject to legislative purpose and constitutional safeguards under Article 25).")

    # Rule 19: Headnote Transparency & Mandatory Verification Disclosure (Directive 13)
    # Answers citing or relying on precedents tagged as 'headnote_only' must disclose that only
    # a headnote summary is available and advise verifying against official/certified text.
    headnote_cits: Set[str] = set()
    if context_chunks:
        for c in context_chunks:
            meta = c.get("metadata", {}) if isinstance(c, dict) else (getattr(c, "metadata", {}) or {})
            c_type = meta.get("content_type") or (c.get("content_type") if isinstance(c, dict) else None)
            raw_t = str(c.get("full_judgment_body") or c.get("text") or c.get("preview") or meta.get("text") or meta.get("full_text") or "")
            if c_type == "headnote_only" or is_compiled_headnote(raw_t):
                cit = meta.get("citation") or meta.get("neutral_citation") or (c.get("citation") if isinstance(c, dict) else None)
                if cit:
                    headnote_cits.add(str(cit).strip())

    # Also extract from query_context if formatted as retrieved precedent blocks
    if "headnote_only" in query_lower:
        blocks = re.findall(r'(?:neutral\s+)?citation:\s*([^\n]+).*?content\s+type:\s*headnote_only', query_context, re.IGNORECASE | re.DOTALL)
        for b_cit in blocks:
            headnote_cits.add(b_cit.strip())

    for h_cit in headnote_cits:
        norm_cit = re.sub(r'[\s_]+', ' ', h_cit).strip().lower()
        clean_key = re.sub(r'[^a-z0-9]', '', norm_cit)
        clean_text = re.sub(r'[^a-z0-9]', '', text_lower)
        if norm_cit and (norm_cit in text_lower or (clean_key and clean_key in clean_text)):
            has_headnote_mention = any(k in text_lower for k in ["headnote", "head-note", "editorial summary", "summary only", "digest summary"])
            has_verify_advice = any(k in text_lower for k in ["verify", "verification", "certified copy", "certified text", "official text", "full judgment text", "original judgment", "primary opinion"])
            if not (has_headnote_mention and has_verify_advice):
                errors.append(
                    f"Citing headnote-only precedent ('{h_cit}') without mandatory transparency disclosure (Directive 13). "
                    "You must explicitly disclose to the advocate that only the reported headnote summary is currently available in the database, "
                    "avoid quoting headnotes as the court's verbatim words, and advise verifying against the official/certified full judgment text."
                )

    # Rule 20: Execution & Property Alienation Procedural Hygiene (Order XXI Rule 96 vs 54, SRA Section 54 vs 39, Section 52 TPA transfer characterization, Section 41 TPA, Section 47 CPC vs Rule 58 / Section 53 TPA, Family Courts Act Section 17)
    # 20.1: Order XXI Rule 96 cited for attachment/restraining alienation (Rule 54 is attachment; Rule 96 is delivery of possession to auction-purchaser)
    if re.search(r'\b(?:order\s+(?:xxi|21)|o\.?\s*(?:xxi|21))[\s,]+rule\s*96\b', text_lower) and any(k in text_lower for k in ["attach", "attachment", "alienat", "restrain", "freez", "prevent transfer"]):
        errors.append(
            "Citing Order XXI Rule 96 CPC for attachment/restraining alienation of property (Order XXI Rule 96 CPC deals solely with delivery of possession to an occupancy tenant or auction-purchaser; the mandatory procedural provision for attachment of immovable property before sale in execution is Order XXI Rule 54 CPC)."
        )

    # 20.2: Section 54 Specific Relief Act cited for cancellation of instruments (Section 39 is cancellation; Section 54 is perpetual injunction)
    if re.search(r'\bsection\s*54\s*(?:of\s*(?:the\s*)?)?(?:specific\s+relief\s+act|sra\b)', text_lower) and any(k in text_lower for k in ["cancel", "cancellation", "set aside", "void deed", "void gift", "void sale"]):
        errors.append(
            "Citing Section 54 Specific Relief Act 1877 for cancellation of deeds/instruments (Section 54 SRA governs perpetual injunctions; the statutory provision for cancellation of void or voidable written instruments/deeds is Section 39 SRA)."
        )

    # 20.3: Section 52 TPA (Lis Pendens) transfer mischaracterized as "void" or "cancelled"
    if re.search(r'\bsection\s*52\s*(?:of\s*(?:the\s*)?)?(?:transfer\s+of\s+property\s+act|tpa\b)', text_lower):
        if re.search(r'\b(?:renders?|makes?|is|are|declared?)\s+(?:the\s+)?(?:transfer|alienation|sale|gift)\s+(?:completely\s+|ab\s+initio\s+|illegal\s+and\s+)?(?:void|null\s+and\s+void|cancelled|invalid\s+ab\s+initio)\b', text_lower) or re.search(r'\btransfers?\s+(?:is|are)\s+void\s+under\s+section\s*52\b', text_lower):
            errors.append(
                "Describing a transfer hit by Section 52 Transfer of Property Act 1882 (Lis Pendens) as 'void' or 'cancelled' (Controlling law: Lis pendens does not render a transfer void ab initio; the transfer remains valid inter partes but is legally subservient and subject to the eventual decree and rights adjudicated in the pending suit)."
            )

    # 20.4: Section 41 TPA bona fide purchaser treated as exception to Section 52 TPA
    if "section 52" in text_lower and "section 41" in text_lower:
        if re.search(r'section\s*41.*(?:exception\s+to\s+section\s*52|protects?.*against\s+section\s*52|overrides?\s+section\s*52|defeats?\s+lis\s+pendens)', text_lower) or re.search(r'bona\s+fide\s+purchaser.*(?:exception\s+to\s+section\s*52|defeats?\s+(?:the\s+rule\s+of\s+)?lis\s+pendens|overrides?\s+section\s*52)', text_lower):
            errors.append(
                "Erroneously asserting that Section 41 TPA (bona fide purchaser protection) protects a transferee against or is an exception to Section 52 TPA (Controlling law: Section 52 lis pendens strictly overrides Section 41 TPA; a transferee pendente lite cannot plead bona fide purchase without notice to defeat a decree in a suit where Section 52 applies)."
            )

    # 20.5: Family Court execution conflating ordinary CPC without Section 17 bar and Section 13 powers
    if any(k in query_lower or k in text_lower for k in ["family court", "maintenance decree", "maintenance suit"]) and any(k in text_lower for k in ["order xxi", "order 21"]):
        if not any(k in text_lower for k in ["section 17", "section 13", "family courts act"]):
            errors.append(
                "Invoking Code of Civil Procedure (Order XXI) for Family Court decree execution without noting the statutory framework of the Family Courts Act 1964 (Section 17 Family Courts Act 1964 expressly bars the application of the CPC to Family Court proceedings, except Sections 10 and 11. Family Court execution is governed specifically by Section 13 of the Family Courts Act 1964 and applicable Family Court Rules)."
            )

    # Rule 21: Case Grounding & Strict Separation of Holding vs. Analogy / Commentary check
    # Check if "Cases Discussed" section includes statutory sections or non-precedents
    if "cases discussed" in text_lower:
        cd_parts = re.split(r'cases\s+discussed', draft_text, flags=re.IGNORECASE)
        if len(cd_parts) > 1:
            cd_section = cd_parts[-1].split("##")[0].split("\n\n\n")[0]
            statutory_leakage = re.findall(r'\b(?:section|sec\.?|order|article|art\.?)\s+\d+', cd_section, re.IGNORECASE)
            if statutory_leakage:
                errors.append(
                    f"'Cases Discussed' section contains statutory citations ({', '.join(statutory_leakage[:3])}) rather than judicial precedents. Only actual judicial case precedents (e.g., PLD, SCMR, YLR) may be listed under Cases Discussed."
                )

    # Check for fabricated doctrines or ratios not in precedent (e.g. four-part test for maintenance transfer)
    if re.search(r'\bfour-?part\s+test\b', text_lower) and any(k in text_lower for k in ["section 52", "maintenance", "tabassum shaheen"]):
        errors.append(
            "Attributing a fabricated 'four-part test' to precedent (no superior court precedent formulates a rigid four-part test applying Section 52 TPA to maintenance suits; statutory ingredients must be quoted directly without inventing multi-factor tests)."
        )

    # Rule 22: Unverified 50% Deposit & Banking Auction Hallucination Interception
    if any(k in text_lower for k in ["50% deposit", "50% pre-deposit", "50 percent deposit", "fifty percent deposit", "50%"]):
        if any(k in text_lower for k in ["order xxi", "order 21", "rule 90", "auction", "fio 2001", "recovery of finances"]):
            is_negated_or_corrected = (
                any(k in text_lower for k in ["no precedent", "not found", "false premise", "unsupported", "not 50%", "no 50%", "does not impose", "neither", "no mandatory 50%"]) or
                bool(re.search(r'\b(?:neither|nor|not|does\s+not|never|no)\b.{0,60}?\b(?:50%|fifty\s+percent|mandatory\s+50%)\b', text_lower))
            )
            is_affirmatively_asserted = (
                bool(re.search(r'\b(?:survived\s+constitutional|upheld\s+against\s+constitutional|tested\s+and\s+upheld|constitutional\s+challenge|constitutionally\s+valid)\b', text_lower)) or
                bool(re.search(r'\b(?:is\s+mandatory|must\s+deposit\s+50%|50%\s+(?:is\s+)?mandatory|statutory\s+requirement\s+is\s+50%|must\s+comply\s+with\s+(?:the\s+)?50%)\b', text_lower))
            )
            if is_affirmatively_asserted and not is_negated_or_corrected:
                errors.append(
                    "Erroneously asserting that a 50% pre-deposit requirement has survived constitutional challenge, is constitutionally valid, or is mandatory under FIO 2001 / Order XXI Rule 90 (The statutory deposit requirement under the second proviso to Order XXI Rule 90 CPC is strictly 20%; no reported precedent establishes a general 50% statutory pre-deposit, and fabricating constitutional approval or statutory status for an ungrounded 50% figure is prohibited)."
                )

    # Rule 23: Universal Precedent Citation Grounding
    # Scans for law reporter citations (SCMR, PLD, CLD, YLR, CLC, MLD, PCrLJ, PTD, PLC, GBLR).
    # If a citation appears in the output, it must appear in the retrieved context chunks (or query_context).
    if context_chunks is not None and full_context_text.strip():
        found_cits = set(re.findall(r'\b(?:19\d{2}|20\d{2})\s+(?:SCMR|PLD|CLD|YLR|CLC|MLD|PCrLJ|PTD|PLC|GBLR)\s+\d+\b', draft_text, re.IGNORECASE))
        found_cits.update(re.findall(r'\bPLD\s+(?:19\d{2}|20\d{2})\s+(?:SC|Lahore|Karachi|Peshawar|Quetta|Supreme Court|High Court)\s+\d+\b', draft_text, re.IGNORECASE))

        ctx_clean = re.sub(r'[^a-z0-9]', '', full_context_text.lower())
        for cit in sorted(found_cits):
            cit_clean = re.sub(r'[^a-z0-9]', '', cit.lower())
            if cit_clean and cit_clean not in ctx_clean:
                errors.append(
                    f"Ungrounded Precedent Citation: '{cit}' appears in generated output but is NOT present in retrieved context chunks."
                )

    # Rule 24: Universal Constitutional Article Grounding
    # Substantive Constitutional Articles (e.g., Article 25, 4, 9, 10-A, 199) cited in output
    # must be grounded in context chunks or query. Articles 189/201/185/175 are standard procedural mentions.
    if context_chunks is not None and full_context_text.strip():
        art_matches = re.finditer(r'\bArticle\s+(\d+[A-Za-z]?(?:-\w+)?)\s+(?:of\s+(?:the\s+)?)?Constitution\b', draft_text, re.IGNORECASE)
        ctx_text_lower = full_context_text.lower()
        seen_articles = set()
        for am in art_matches:
            art_raw = am.group(1)
            art_num = art_raw.lower()
            if art_num in seen_articles:
                continue
            seen_articles.add(art_num)
            if art_num in ["189", "201", "185", "175"]:
                continue
            art_pattern = rf'\barticle\s*{re.escape(art_num)}\b'
            if not re.search(art_pattern, ctx_text_lower) and not re.search(art_pattern, query_lower):
                errors.append(
                    f"Ungrounded Constitutional Article: 'Article {art_raw}' is cited in generated output but does not appear in retrieved context chunks or query."
                )

    # Rule 25: Headnote Quote Discipline (Nuanced Quote Rule)
    # Quoting headnote text is permitted ONLY when explicitly introduced as reported headnote text
    # (e.g., "The reported headnote states: '...'"). Attributing headnote text to judicial speech
    # ("The Court held: '...'", "The Supreme Court stated: '...'") is strictly forbidden.
    if headnote_cits:
        for h_cit in headnote_cits:
            norm_cit = re.sub(r'[\s_]+', ' ', h_cit).strip().lower()
            clean_h_cit = re.sub(r'[^a-z0-9]', '', norm_cit)
            if norm_cit in text_lower or (clean_h_cit and clean_h_cit in re.sub(r'[^a-z0-9]', '', text_lower)):
                court_speech_patterns = [
                    rf'{re.escape(norm_cit)}[^\.\n]*?(?:the\s+court|the\s+supreme\s+court|the\s+high\s+court|the\s+bench)\s+(?:held|stated|observed|ruled|noted|declared)\s*[:,]?\s*["“]',
                    rf'(?:the\s+court|the\s+supreme\s+court|the\s+high\s+court|the\s+bench)\s+(?:held|stated|observed|ruled|noted|declared)\s*[:,]?\s*["“][^"”]+["”][^\.\n]*?{re.escape(norm_cit)}',
                ]
                for csp in court_speech_patterns:
                    if re.search(csp, text_lower):
                        errors.append(
                            f"Headnote Quoting Violation: Attributing headnote text to judicial speech for '{h_cit}'. "
                            f"Precedents indexed as 'headnote_only' may only be quoted if explicitly introduced as reported headnote text ('The reported headnote states: ...')."
                        )
                        break

    # Rule 26: Holding Scope & 20%/50% Reconciliation
    # Ratios must not exceed the source text. Dismissal for failure to comply with a court direction
    # cannot be framed as a substantive ruling that 50% is lawful or non-waivable on quantum.
    # Where court-directed deposit differs from the statutory 20% proviso, output must state that the legal
    # basis for demanding >20% is not addressed in retrieved sources (rather than calling 50% "non-waivable").
    if any(k in text_lower for k in ["50% deposit", "50% pre-deposit", "fifty percent", "50%"]):
        if re.search(r'\b50%\s+(?:is\s+)?(?:non-waivable|a\s+substantive\s+rule|statutory\s+quantum|held\s+to\s+be\s+lawful\s+on\s+quantum)\b', text_lower):
            errors.append(
                "Over-claiming precedent holding: A dismissal for failure to comply with a court deposit direction cannot be framed as a substantive ruling that a 50% deposit is non-waivable or lawful on quantum."
            )

    if re.search(r'\bpartition\b', text_lower) and any(k in text_lower for k in ["fio 2001", "banking court", "mortgage execution"]):
        errors.append(
            "Domain Misattribution: Citing partition execution authorities as governing banking mortgage execution under FIO 2001."
        )

    return errors



def handle_reflection_or_abort(llm_client, original_prompt: str, generated_text: str, context_chunks: List[Any]) -> str:
    """
    Executes a single reflection step. If the context cannot support the correction,
    it aborts rather than entering an infinite hallucination cycle.
    """
    context_str = " ".join([
        (c.get("metadata", {}).get("text") or c.get("text", "") if isinstance(c, dict) else str(c))
        for c in (context_chunks or [])
    ])
    lint_errors = lint_legal_output(generated_text, query_context=context_str)
    if not lint_errors:
        return generated_text

    # If errors were due to missing information in the context, abort cleanly
    for err in lint_errors:
        if "Hallucinated" in err or "Synthesized" in err or "not present in retrieved context" in err or "Citing phantom section" in err:
            return (
                "The available verified database does not contain a direct precedent or statutory holding addressing this specific question. "
                "Citations generated during verification were excluded to prevent inaccurate legal references."
            )

    return generated_text


def is_structural_or_title_quote(quote_text: str) -> bool:
    """
    Ignore short quotes, title-case headings, or typical LLM structural wrappers.
    Prevents structural headers, bullet titles, or case name phrases wrapped in quotes
    from triggering the Unverified Quotation Notice.
    """
    if not quote_text or not isinstance(quote_text, str):
        return True
    cleaned = quote_text.strip()
    if len(cleaned.split()) <= 6 or cleaned.endswith(":") or cleaned.endswith("—"):
        return True
    return False


def sanitize_unverified_quotes(generated_text: str, unverified_quotes: List[str]) -> str:
    """
    Option A: Silent Sanitization.
    Takes the generated LLM text and a list of unverified quote strings.
    Instead of exposing warning banners, it quietly strips quotation marks 
    from unverified extractions, converting them into smooth, unquoted prose.
    """
    if not generated_text or not unverified_quotes:
        return generated_text

    sanitized_text = generated_text

    for quote in unverified_quotes:
        if not quote:
            continue

        # Common quote formatting variants generated by LLMs
        double_quoted = f'"{quote}"'
        smart_double = f'“{quote}”'
        single_quoted = f"'{quote}'"
        smart_single = f'‘{quote}’'

        # Replace quoted variants with clean, unquoted text
        if double_quoted in sanitized_text:
            sanitized_text = sanitized_text.replace(double_quoted, quote)
        elif smart_double in sanitized_text:
            sanitized_text = sanitized_text.replace(smart_double, quote)
        elif single_quoted in sanitized_text:
            sanitized_text = sanitized_text.replace(single_quoted, quote)
        elif smart_single in sanitized_text:
            sanitized_text = sanitized_text.replace(smart_single, quote)
        else:
            q_strip = quote.strip()
            pattern = r'["“\'‘]\s*' + re.escape(q_strip) + r'\s*["”\'’]'
            sanitized_text = re.sub(pattern, q_strip, sanitized_text)

    return sanitized_text


def verify_case_grounding(cited_case_name: str, source_judgment_text: str, model_assertion: str) -> Dict[str, Any]:
    """
    Verifies that a legal proposition or ratio attributed to a cited precedent
    is actually entailed by the source judgment text, rather than being an LLM
    extrapolation, speculative inference, or blended analogical commentary.
    
    Args:
        cited_case_name: The name or citation of the case (e.g., 'Tabassum Shaheen v. Mst. Tasneem Akhtar', '2025 PLD 63').
        source_judgment_text: The retrieved raw or full text of the judgment.
        model_assertion: The text/holding written by the LLM attributing a specific ratio to the case.
        
    Returns:
        {
            "is_grounded": bool,
            "cited_case": str,
            "entailment_score": float,  # 0.0 to 1.0
            "unsupported_propositions": List[str],
            "reason": str
        }
    """
    if not source_judgment_text or not source_judgment_text.strip():
        return {
            "is_grounded": False,
            "cited_case": cited_case_name,
            "entailment_score": 0.0,
            "unsupported_propositions": ["Source judgment text is empty or missing from retrieved context."],
            "reason": "Missing source judgment text for verification."
        }

    src_lower = source_judgment_text.lower()
    assertion_lower = model_assertion.lower()

    unsupported: List[str] = []

    # 1. Check for specific statutory sections asserted as held or applied in the case
    assertion_secs = re.findall(r'\b(?:section|sec\.?|s\.)\s*(\d+[a-z]?)\b', assertion_lower)
    for sec in set(assertion_secs):
        sec_num = sec.lower()
        pattern = rf'\b(?:section|sec\.?|s\.)\s*{re.escape(sec_num)}\b'
        if not re.search(pattern, src_lower) and not re.search(rf'\b{re.escape(sec_num)}\b', src_lower):
            unsupported.append(
                f"Assertion claims the court held or applied Section {sec.upper()}, but Section {sec.upper()} does not appear in the source judgment."
            )

    # 1b. Check for procedural orders/rules asserted as held or applied in the case
    assertion_orders = re.findall(r'\b(?:order|ord\.?|o\.)\s*[ivxlcdm\d]+[\s,]+(?:rule|r\.?)\s*\d+[a-z]?\b', assertion_lower)
    for ord_rule in set(assertion_orders):
        if not is_statute_in_source(ord_rule, source_judgment_text):
            unsupported.append(
                f"Assertion claims the court held or applied {ord_rule.title()}, but that provision does not appear in the source judgment."
            )

    # 2. Check for asserted subject-matter domains that may be entirely absent from the source judgment
    domain_terms = {
        "maintenance": ["maintenance", "kharch", "dower", "minor children", "child support"],
        "pre-emption": ["pre-emption", "preemption", "talb", "shufa"],
        "cheque dishonour": ["cheque", "dishonour", "dishonor", "489-f"],
        "narcotics": ["narcotics", "cnsa", "charas", "heroin", "chain of custody"],
        "tax assessment": ["tax assessment", "income tax", "ito 2001", "commissioner inland revenue"],
    }

    for domain, terms in domain_terms.items():
        if any(t in assertion_lower for t in terms):
            if not any(t in src_lower for t in terms):
                unsupported.append(
                    f"Assertion purports that {cited_case_name} adjudicated or established a rule regarding '{domain}', but the source judgment contains no discussion of {domain}."
                )

    # 3. Check for fabricated structural assertions (e.g., "four-part test", "three-pronged test", "presumption of fraud")
    fabricated_doctrines = [
        ("four-part test", r'\bfour-?part\s+test\b'),
        ("three-pronged test", r'\bthree-?pronged\s+test\b'),
        ("presumption of fraud on relatives", r'presumption\s+of\s+fraud.*(?:relative|family|kin|maintenance)'),
    ]
    for doc_name, doc_pattern in fabricated_doctrines:
        if re.search(doc_pattern, assertion_lower):
            if not re.search(doc_pattern, src_lower):
                unsupported.append(f"Assertion attributes a '{doc_name}' to the judgment which does not exist in the source text.")

    # 4. Check for ungrounded procedural claims (e.g., claiming the judgment applied or mandated Order XXI Rule 96 or Section 54 SRA)
    if "order xxi rule 96" in assertion_lower and "rule 96" not in src_lower:
        unsupported.append("Assertion claims the judgment applied or mandated Order XXI Rule 96, which is absent in the source judgment.")
    if "section 54" in assertion_lower and "specific relief act" in assertion_lower and "section 54" not in src_lower:
        unsupported.append("Assertion claims the judgment cancelled an instrument under Section 54 SRA, which does not appear in the source judgment.")

    # Calculate entailment score
    if unsupported:
        penalty = min(0.35 * len(unsupported), 1.0)
        entailment_score = round(max(0.0, 1.0 - penalty), 2)
        is_grounded = entailment_score >= 0.70 and len(unsupported) == 0
    else:
        entailment_score = 1.0
        is_grounded = True

    reason = "Case holding is grounded in source judgment text." if is_grounded else f"Attribution ungrounded: {'; '.join(unsupported)}"

    return {
        "is_grounded": is_grounded,
        "cited_case": cited_case_name,
        "entailment_score": entailment_score,
        "unsupported_propositions": unsupported,
        "reason": reason
    }


def decompose_compound_legal_query(query: str) -> List[str]:
    """
    Decomposes a compound, multi-issue legal research query into focused sub-queries
    to prevent semantic vector dilution and ensure every sub-issue retrieves dedicated
    candidate precedents.
    
    If the query is focused on a single topic, returns [query].
    """
    if not query or not isinstance(query, str):
        return [query] if query else []

    q_clean = query.strip()
    q_lower = q_clean.lower()

    subqueries: List[str] = []

    # 1. Deposit / Pre-deposit aspect
    if any(k in q_lower for k in ["deposit", "pre-deposit", "20%", "50%", "security deposit"]):
        statute_ctx = "FIO 2001 Order XXI Rule 90" if any(k in q_lower for k in ["fio", "banking", "auction", "order xxi", "rule 90"]) else ""
        subqueries.append(f"mandatory pre-deposit auction objection {statute_ctx}".strip())

    # 2. Constitutional validity / challenge aspect
    if any(k in q_lower for k in ["constitutional", "constitutionality", "vires", "article 199", "ultra vires", "fundamental rights"]):
        subqueries.append("constitutional challenge vires mandatory deposit auction objection execution")

    # 3. Proclamation / Publication / Notice defect aspect
    if any(k in q_lower for k in ["proclamation", "sale proclamation", "publication", "rule 66", "rule 67", "material irregularity"]):
        statute_ctx = "Section 19 FIO 2001 Order XXI Rule 90" if any(k in q_lower for k in ["fio", "banking", "auction"]) else "Order XXI CPC"
        subqueries.append(f"auction sale proclamation defect publication material irregularity {statute_ctx}".strip())

    # 4. Reserve price / Valuation / Market value aspect
    if any(k in q_lower for k in ["reserve price", "minimum price", "valuation", "market value", "low price", "inadequate price"]):
        statute_ctx = "Section 19 FIO 2001 Banking Court" if any(k in q_lower for k in ["fio", "banking"]) else "Order XXI Rule 90"
        subqueries.append(f"reserve price valuation fixation mortgaged property auction {statute_ctx}".strip())

    # 5. Fraud / Collusion / Stranger aspect
    if any(k in q_lower for k in ["fraud", "collusion", "fraudulent", "substantial injury"]):
        subqueries.append("setting aside auction sale fraud substantial injury Order XXI Rule 90")

    # If subqueries were identified and there are at least 2 distinct prongs, return them alongside a normalized core query
    if len(subqueries) >= 2:
        result = [q_clean]
        for sq in subqueries:
            if sq not in result:
                result.append(sq)
        return result

    # Check for sentence or conjunction-separated clauses if long
    if len(q_clean.split()) >= 14 and any(sep in q_clean for sep in [";", "\n", " and also ", " as well as "]):
        parts = re.split(r'[;\n]|\band also\b|\bas well as\b', q_clean, flags=re.IGNORECASE)
        valid_parts = [p.strip() for p in parts if len(p.strip().split()) >= 3]
        if len(valid_parts) >= 2:
            return [q_clean] + valid_parts

    return [q_clean]


def check_memo_completeness(text: str, is_formal_opinion: bool = True) -> Tuple[bool, List[str]]:
    """
    Verifies that a generated legal memorandum contains all required sections
    (min 40 words per section) and parseable <<<CARDS>>> JSON.
    
    Returns (is_complete: bool, missing_or_short_sections: List[str]).
    """
    if not text or not isinstance(text, str):
        return False, ["Memo text is empty"]

    if not is_formal_opinion:
        return True, []

    required_sections = [
        ("Executive Summary", r'###\s*(?:I\.\s*)?EXECUTIVE\s*SUMMARY'),
        ("Statutory Framework", r'###\s*(?:II\.\s*)?(?:CONTROLLING\s*STATUTORY|STATUTORY\s*&\s*PROCEDURAL|GOVERNING\s*STATUTORY|STATUTORY\s*FRAMEWORK)'),
        ("Precedents", r'###\s*(?:III\.\s*)?(?:CONTROLLING\s*JUDICIAL|CASE\s*LAW|BINDING\s*&\s*PERSUASIVE|APPELLATE\s*PRECEDENTS|PRECEDENTS)'),
        ("Legal Analysis", r'###\s*(?:IV\.\s*)?(?:LEGAL\s*ANALYSIS|STRATEGIC\s*LEGAL|PROCEDURAL\s*&\s*STRATEGIC|ANALYSIS)'),
        ("Recommendations / Next Steps", r'###\s*(?:V\.\s*)?(?:RECOMMENDATIONS|PRACTICAL\s*NEXT|NEXT\s*STEPS|PROCEDURAL\s*ROADMAP|PLAYBOOK)'),
    ]

    issues = []
    for sec_name, pattern in required_sections:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            issues.append(f"Missing section: '{sec_name}'")
        else:
            start_pos = match.end()
            next_header = re.search(r'(?:###|<<<CARDS>>>)', text[start_pos:])
            sec_body = text[start_pos:start_pos + next_header.start()] if next_header else text[start_pos:]
            words = sec_body.strip().split()
            if len(words) < 40:
                issues.append(f"Section '{sec_name}' is too brief ({len(words)} words; min 40 words required)")

    if "<<<CARDS>>>" in text:
        cards_match = re.search(r'<<<CARDS>>>(.*?)(?:<<<END_CARDS>>>|$)', text, re.DOTALL)
        if not cards_match or not cards_match.group(1).strip():
            issues.append("Empty <<<CARDS>>> block")
        else:
            cards_content = cards_match.group(1).strip()
            try:
                parsed = json.loads(cards_content)
                if not isinstance(parsed, list):
                    issues.append("<<<CARDS>>> JSON is not an array")
            except Exception as e:
                issues.append(f"Invalid <<<CARDS>>> JSON syntax: {e}")

    is_complete = len(issues) == 0
    return is_complete, issues




