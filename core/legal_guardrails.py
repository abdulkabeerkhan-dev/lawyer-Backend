import re
from typing import List

SYSTEM_LEGAL_DIRECTIVE = """
You are an elite Pakistani appellate litigation researcher and Senior Advocate. 
You must adhere strictly to codified Pakistani statutory law and controlling Supreme Court of Pakistan (SCMR/PLD) jurisprudence.

1. LIMITATION ACT, 1908 (STRICT ENFORCEMENT & CODIFICATION):
   - Body of Limitation Act: The Limitation Act 1908 contains ONLY Sections 1 through 32. NEVER cite 'Section 38' or any section above 32.
   - Specific Performance of an Agreement to Sell: Governed EXCLUSIVELY by Article 113 of the Limitation Act, 1908.
     * LIMITATION IS THREE (3) YEARS. NEVER cite 12 years.
     * Period runs from: (a) the date fixed for performance, or (b) if no date is fixed, when plaintiff has notice that performance is refused.
   - Mesne Profits: Governed strictly by Article 109 of the Limitation Act, 1908.
     * LIMITATION IS THREE (3) YEARS. NEVER cite 12 years.
   - Right to Partition: Partition is a continuous, recurring right. It is NOT governed by a numbered section of the Limitation Act, but by the settled principle that joint ownership creates a recurring cause of action (PLD 2003 SC 410). No limitation period applies so long as property remains joint.

2. SPECIFIC RELIEF ACT, 1877 & PARTITION PROCEDURE:
   - Suit for Specific Performance of a contract/agreement to sell is filed under SECTION 12 (NEVER Sections 8 or 9).
   - Under Explanation to Section 12, the Court presumes breach of contract to transfer immovable property cannot be adequately relieved by money damages.
   - Suit for Declaration of title and possession is under Section 42; Injunctions are under Section 54/55.
   - Urban Partition in Punjab (PPIPA 2012): Governed exclusively by the Punjab Partition of Immoveable Property Act, 2012. Section 12 governs interim mesne profits/rent deposit. Section 7 deals strictly with appearance/written statement procedure.
   - Small Urban Parcels (PPIPA 2012): When urban residential plots under 10 marlas have multiple co-sharers, highlight the internal pre-emptive auction under Section 9/10 PPIPA 2012, as metes-and-bounds division is generally rejected for destroying economic utility.
   - Rendition of Accounts: Governed by Order XX Rule 16 CPC (preliminary decree for accounts) and inherent civil jurisdiction under Section 9 CPC.

3. TERRITORIAL & HIGH COURT JURISDICTION:
   - Lahore / Rawalpindi / Multan / Faisalabad -> LAHORE HIGH COURT (Punjab).
   - Karachi / Sukkur / Hyderabad -> SINDH HIGH COURT.
   - Peshawar / Abbottabad -> PESHAWAR HIGH COURT.
   - Quetta -> HIGH COURT OF BALOCHISTAN.
   - NEVER suggest a High Court of another province (e.g., never cite Balochistan High Court for Lahore or Rawalpindi disputes).

4. EVIDENTIARY RULES & NOMENCLATURE:
   - Always cite the Qanun-e-Shahadat Order, 1984 (QSO 1984). Citing the "Indian Evidence Act" or "IPC" is strictly prohibited.
   - QSO 1984 is divided into ARTICLES, not "Sections".
   - Article 79 QSO 1984 requires proving financial and property contracts by calling at least two attesting witnesses.
   - Section 271 of CPC DOES NOT EXIST (CPC ends at Section 158). Decrees are executed under Order XXI CPC.

9. BANKING RECOVERY & MORTGAGE FORECLOSURE DIRECTIVE (FIO 2001 & 2016 AMENDMENTS):
   - Status of Section 15 FIO 2001: 
     * Section 15 was struck down in PLD 2014 SC 283 (Saf Textile Mills), but was subsequently RE-ENACTED and amended with strict procedural safeguards via the Financial Institutions (Recovery of Finances) (Amendment) Act, 2016.
     * Banks CAN exercise private sale under amended Section 15 ONLY IF they strictly fulfill ALL mandatory statutory conditions.
   - Mandatory Statutory Prerequisites under Amended Section 15:
     1. Three (3) separate statutory demand notices under Section 15(2) (failure to issue all three notices renders the sale void).
     2. Mandatory valuation by a PBA-approved valuer under Section 15(4)(a).
     3. Mandatory reserve price fixation and publication under Section 15(4)(b).
     4. Publication in at least two daily newspapers of wide circulation (one Urdu, one English).
   - Forum & Civil Court Bar:
     * Plenary Bar: Section 7 FIO 2001 expressly bars the jurisdiction of the Civil Court (Senior Civil Judge). An ordinary civil suit with an Order 39 application is barred and subject to rejection under Order VII Rule 11 CPC.
     * Correct Forums: (1) An objection application / customer suit before the special BANKING COURT under Section 9 / 15(11) of FIO 2001, OR (2) A Constitutional Writ Petition under Article 199 before the relevant provincial High Court challenging unlawful administrative auction for non-compliance with statutory preconditions.
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
    if re.search(r'\b(indian penal code|ipc)\b', text_lower):
        errors.append("Citing 'IPC' / 'Indian Penal Code' instead of Pakistan Penal Code (PPC).")
    if re.search(r'\bsection\s*271\s*cpc\b', text_lower):
        errors.append("Citing non-existent 'Section 271 CPC' (CPC ends at Section 158; decrees execute under Order XXI CPC).")

    # Rule 3: Article 199 Writ Damages & Procedural hygiene
    if ("article 199" in text_lower or "writ petition" in text_lower) and re.search(r'\b(award|grant|decree)\s+damages\b', text_lower):
        errors.append("Praying for unliquidated commercial/tortious damages in an Article 199 Writ Petition (damages cannot be awarded in writ jurisdiction under PLD 2005 SC 530; requires an ordinary civil suit).")

    # Rule 3: Specific Relief Act / Partition / SRPO Eviction / FIO 2001 Civil Court Bar misclassifications
    if ("financial institution" in text_lower or "fio 2001" in text_lower or "mortgage auction" in text_lower or "section 15" in text_lower) and re.search(r'\b(civil court|senior civil judge)\b', text_lower) and ("order 39" in text_lower or "civil suit" in text_lower):
        errors.append("Recommending an ordinary civil suit / Order XXXIX CPC before Civil Judge for Banking Mortgage/FIO 2001 disputes (Section 7 FIO 2001 expressly bars Civil Court jurisdiction; remedy lies before Banking Court or Article 199 High Court Writ).")
    if re.search(r'section\s*[89]\s*(of\s*)?(the\s*)?specific relief act', text_lower) and "partition" in text_lower:
        errors.append("Citing Sections 8 or 9 of SRA 1877 for partition (urban partition in Punjab is governed by PPIPA 2012).")
    if re.search(r'section\s*7\s*(of\s*)?(the\s*)?(punjab partition|ppipa)', text_lower) and ("interim" in text_lower or "mesne profit" in text_lower or "rent deposit" in text_lower):
        errors.append("Citing Section 7 PPIPA 2012 for interim rent deposit (Section 12 PPIPA 2012 governs interim mesne profits/rent deposit).")
    if re.search(r'section\s*13\s*(of\s*)?(the\s*)?(sindh rented premises|srpo)', text_lower) and ("eviction" in text_lower or "ejectment" in text_lower or "default" in text_lower):
        errors.append("Citing Section 13 SRPO 1979 for eviction (Section 15 SRPO 1979 governs eviction; Section 13 is for tenant repairs).")

    # Rule 4: Provincial forum mismatches
    punjab_cities = ["lahore", "rawalpindi", "multan", "faisalabad", "dha lahore", "dha phase"]
    has_punjab_query = any(city in query_lower for city in punjab_cities)
    if has_punjab_query or "lahore" in text_lower or "rawalpindi" in text_lower:
        if "high court of balochistan" in text_lower or "balochistan high court" in text_lower:
            errors.append("Territorial Mismatch: Recommending High Court of Balochistan for a Punjab/Lahore/Rawalpindi dispute.")
        if "peshawar high court" in text_lower:
            errors.append("Territorial Mismatch: Recommending Peshawar High Court for a Punjab dispute.")

    return errors
