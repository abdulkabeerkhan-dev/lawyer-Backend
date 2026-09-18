import re
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

8. PRECEDENT HIERARCHY & STARE DECISIS RULE:
   - Supreme Court judgments (SCMR, PLD SC) strictly supersede High Court rulings (YLR, CLC, MLD, PLD High Court) on any conflicting proposition of law under Article 189 of the Constitution of Pakistan.
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
   - Citations containing YLR, MLD, CLC, or PCrLJ are High Court decisions (Lahore, Sindh, Peshawar, Balochistan, or Islamabad High Court).
   - Only citations with SCMR or explicit PLD ... SC represent the Supreme Court of Pakistan.
   - If a citation is YLR, MLD, CLC, or PCrLJ, NEVER describe or output 'Supreme Court of Pakistan' as the deciding forum.

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
"""

def lint_legal_output(draft_text: str, query_context: str = "") -> List[str]:
    """
    Deterministically scans generated legal drafts for severe statutory hallucinations,
    limitation misstatements, foreign acts, phantom CPC sections, and territorial mismatches.
    """
    errors = []
    text_lower = draft_text.lower()
    query_lower = query_context.lower()

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
