"""
tests/test_structural_judgment_segmenter.py

Unit Test Suite for Structural Legal Judgment Segmenter & Domain Classifier.
Tests:
- Mixed Headnote + Full Judgment segregation (2006 YLR 2059)
- Headnote-Only Digest segregation (2026 SCMR 941)
- Criminal Bail / 420 PPC domain isolation
- Family Law (Khula) domain isolation
- Banking FIO 2001 domain isolation
- Pinecone multi-segment metadata payload schema validation
"""

import pytest
from core.structural_judgment_segmenter import StructuralJudgmentSegmenter


SAMPLE_2006_YLR_2059 = """
2006 Y L R 2059
[Lahore]
Before Jawwad S. Khawaja, J
Khawaja NAYYAR QAYYUM---Petitioner
Versus
ZUBAIR QAYYUM and 6 others---Respondents
Civil Revision No.485-D of 1992, heard on 8th July, 2003.

Partition Act (IV of 1893)---
----Ss. 2 & 3---Partial partition---Benamidar---Partition and separate possession was sought of ancestral house---One of the defendants contested the suit, by taking the plea that their predecessor-in interest was owner of two other properties which properties were held by Benamidars, and were not included in the partition suit, suit was thus not maintainable because partial partition was sought---Trial Court rejected the plea and passed preliminary decree---Appellate Court reversed the findings of trial Court holding that "benami" held properties be also dealt with in the partition proceedings and remanded the case---Judgment of the appellate Court was not legally sustainable as the plaintiff was entitled to confine his suit to the property held by his predecessor-in interest---Plaintiff was not owner of such properties which were in the name of other persons---If the defendant had any claim on such properties he should have filed separate suit for declaration---Judgment and decree of the appellate Court were set aside and judgment and decree of the trial Court were restored.

Malik Abdul Wahid for Petitioner.
Malik Mushtaq Ahmad for Respondent No. 1.

JUDGMENT

JAWWAD S. KHAWAJA, J.--This revision petition arises out of a suit filed by Khawaja Nayyar Qayyum (plaintiff/petitioner) seeking possession through partition, of his share in the property fully described in paragraph 1 of the plaint. The said property was owned by Abdul Qayyum, who is the common predecessor-in-interest of the parties to this revision petition.

2. Respondents Nos.2 to 7, who were impleaded as defendants in the partition suit, submitted a conceding written statement. Only Zubair Qayyum respondent No.1 contested the suit. In his written statement, he took up the plea that late Abdul Qayyum was owner of two other properties also, namely, Wyne House and Kothi No.94, although Wyne House was owned Benami in the name of respondent No.6 Fahmida Begum. On this basis, it was contended that the partition suit filed by the petitioner/ plaintiff was not maintainable because he had sought partial partition.

3. The learned trial Court decreed the partition suit vide judgment and preliminary decree dated 11-6-1988 under Order XX Rule 18 CPC. Feeling aggrieved, Zubair Qayyum respondent No.1 preferred an appeal. The learned lower appellate Court reversed the finding of the learned trial Court on Issue No.2 holding that the two other properties also had to be dealt with in the present proceedings.

4. I have gone through the impugned appellate judgment, with the assistance of both learned counsel, and find that the same is not legally sustainable. The petitioner/ plaintiff was entitled to confine his suit to the property described in the plaint, which admittedly was owned by Abdul Qayyum, predecessor-in-interest of the parties. The suit filed by the petitioner was a partition suit and not an administration suit in which all properties of Abdul Qayyum had to be consolidated. Furthermore, the other properties quite clearly were not owned by the late Abdul Qayyum. If at all, Zubair Qayyum (respondent No.1) had any claim, he could separately have initiated proceedings by claiming declaration of title in the said properties.

5. In the foregoing circumstances, the judgment and decree of the learned lower appellate Court is set aside. Revision accepted.
"""

SAMPLE_2026_SCMR_941 = """
Citation Name: 2026 SCMR 941 SUPREME-COURT
Bookmark this Case 

SHAHBAZ KHAN VS DOWLAT KHAN

O.XX, R.18 Partition of ancestral estate Family settlement Selective claim over disputed property by one heir Partial partition of property, permissibility of Preliminary decree Mandatory determination of shares Failure to specify shares Material irregularity Present matter concerned a dispute between three brothers over the partition of property left by their deceased father, comprising four houses. A preliminary decree was passed without specifying the shares of the parties. Held: The suit concerned the partition of property along with a request for separate possession of an individual share Given this context it was imperative that the Trial Court adhered to the procedural guidelines set out in Rule 18 of Order XX, C.P.C. when issuing preliminary decree Unfortunately, this essential procedure was overlooked Judgments and decrees rendered by the Courts below were unsustainable. Matter was referred back to the Trial Court to decide the suit afresh in accordance with law. Petition was converted into appeal and allowed.

O.XX, R.18 Suit for partial partition Maintainability Scope A party choosing to seek partition should not have the liberty to selectively choose and acquire a share in the more valuable aspects of the joint holdings while simultaneously excluding those portions of lesser value. Each co-owner possesses ownership rights over every inch of the joint holding corresponding to their share. Therefore, it is inappropriate for any part of the joint holding to be permitted for separate partition. Entire property corpus is aggregated into a common pool under Partition Act 1893.
"""

SAMPLE_CRIMINAL_420 = """
2024 PCrLJ 550
[Lahore]
Before Ali Baqar Najafi, J
TARIQ MEHMOOD---Petitioner Versus THE STATE---Respondent
Criminal Miscellaneous No.12345-B of 2024, decided on 15th March, 2024.

Penal Code (XLV of 1860)---
----Ss. 406 & 420---Criminal breach of trust and cheating---Commercial dispute---Pre-arrest bail, grant of---FIR registered alleging failure to supply cotton bales after receiving advance payment---Held: Transaction between the parties arose out of an agreement to sell and commercial dealing---Non-performance of contractual promise does not per se constitute criminal offence of cheating under Section 420 PPC or criminal breach of trust under Section 406 PPC in absence of dishonest intention at inception---Criminal machinery cannot be activated as a recovery forum for civil debt---Petitioner has joined investigation and ad-interim pre-arrest bail is confirmed under Section 498 Cr.P.C.
"""

SAMPLE_FAMILY_KHULA = """
2025 CLC 120
[Karachi]
Before Kausar Sultana Hussain, J
Mst. SABA---Petitioner Versus ADNAN---Respondent
Family Appeal No.55 of 2024, decided on 10th January, 2025.

Family Courts Act (XXXV of 1964)---
----S. 10(4) & (5)---Muslim Family Laws Ordinance (VIII of 1961), S. 8---Dissolution of marriage on the ground of Khula---Failure of pre-trial reconciliation---Decree for dissolution of marriage by Khula passed by Family Court---Husband challenged the decree on ground that he had not given consent and dower was not returned---Held: Under Section 10(4) of the Family Courts Act 1964, upon failure of reconciliation, the Family Court is under mandatory statutory duty to immediately pass a decree for dissolution of marriage on ground of Khula---Consent of husband is not a prerequisite for Khula decree as established by Supreme Court in PLD 1967 SC 97 (Khurshid Bibi case)---Non-return of Zar-i-Khula is a civil liability and does not invalidate the dissolution decree---Appeal dismissed.
"""

SAMPLE_BANKING_FIO = """
2026 CLD 292
[Lahore]
Before Shahid Karim, J
SALMAN CAPITAL INVESTMENTS LTD.---Petitioner Versus HABIB BANK LIMITED---Respondent
Banking Case No.10 of 2025, decided on 5th February, 2026.

Financial Institutions (Recovery of Finances) Ordinance (XLVI of 2001)---
----Ss. 9 & 10---Suit for recovery of finance---Leave to defend suit---Conditional leave---Customer sought unconditional leave claiming disputed markup calculation---Banking Court granted leave subject to furnishing cash deposit of 50% of suit amount---Held: Under Section 10 of FIO 2001, leave to defend can only be granted if application discloses substantial questions of law or fact---Failure to specifically dispute statement of account disentitles customer to unconditional leave---Order of Banking Court upheld.
"""


def test_segment_mixed_case():
    meta = {
        "case_id": "2006_YLR_2059",
        "citation": "2006 YLR 2059",
        "case_title": "Khawaja Nayyar Qayyum v. Zubair Qayyum",
        "court_name": "Lahore High Court",
        "decision_date": "2006-01-01"
    }
    res = StructuralJudgmentSegmenter.segment_judgment(SAMPLE_2006_YLR_2059, metadata=meta)

    assert res["case_id"] == "2006_YLR_2059"
    assert res["citation"] == "2006 YLR 2059"
    assert res["detected_type"] == "mixed"
    assert res["domain"] == "civil"
    assert res["subdomain"] == "partition"
    assert "Partition Act, 1893" in res["statutes_cited"]
    assert "Code of Civil Procedure, 1908" in res["statutes_cited"]
    assert "Order XX Rule 18 CPC" in res["provisions_cited"]
    assert res["has_full_text"] is True

    # Check Headnote Segment
    assert "Partial partition---Benamidar" in res["headnote_segment"]
    assert "JUDGMENT" not in res["headnote_segment"]

    # Check Ratio Decidendi Segment
    assert "not an administration suit" in res["ratio_decidendi_segment"]
    assert "entitled to confine his suit" in res["ratio_decidendi_segment"]

    # Check Pinecone multi-segment vectors
    segments = res["pinecone_segments"]
    assert len(segments) >= 2
    seg_types = [s["segment_type"] for s in segments]
    assert "headnote" in seg_types
    assert "ratio_decidendi" in seg_types

    # Check metadata fields for Pinecone pre-filtering
    for seg in segments:
        m = seg["metadata"]
        assert m["domain"] == "civil"
        assert m["subdomain"] == "partition"
        assert "Partition Act, 1893" in m["statutes"]
        assert m["case_id"] == "2006_YLR_2059"


def test_segment_headnote_only_case():
    meta = {
        "case_id": "2026_SCMR_941",
        "citation": "2026 SCMR 941",
        "case_title": "Shahbaz Khan v. Dowlat Khan",
        "court_name": "Supreme Court of Pakistan",
        "decision_date": "2026-01-01"
    }
    res = StructuralJudgmentSegmenter.segment_judgment(SAMPLE_2026_SCMR_941, metadata=meta)

    assert res["case_id"] == "2026_SCMR_941"
    assert res["detected_type"] == "headnote_only"
    assert res["domain"] == "civil"
    assert res["subdomain"] == "partition"
    assert "Code of Civil Procedure, 1908" in res["statutes_cited"]
    assert "Order XX Rule 18 CPC" in res["provisions_cited"]
    assert len(res["headnote_segment"]) > 100
    assert "Order XX Rule 18" in res["ratio_decidendi_segment"] or "preliminary decree" in res["ratio_decidendi_segment"].lower()


def test_segment_criminal_case():
    meta = {
        "case_id": "2024_PCrLJ_550",
        "citation": "2024 PCrLJ 550",
        "case_title": "Tariq Mehmood v. The State",
        "court_name": "Lahore High Court",
        "decision_date": "2024-03-15"
    }
    res = StructuralJudgmentSegmenter.segment_judgment(SAMPLE_CRIMINAL_420, metadata=meta)

    assert res["domain"] == "criminal"
    assert res["subdomain"] in ["bail_pre_arrest", "fraud_and_cheating"]
    assert "Pakistan Penal Code, 1860" in res["statutes_cited"]
    assert "Code of Criminal Procedure, 1898" in res["statutes_cited"]
    assert any("420" in p or "406" in p for p in res["provisions_cited"])


def test_segment_family_case():
    meta = {
        "case_id": "2025_CLC_120",
        "citation": "2025 CLC 120",
        "case_title": "Mst. Saba v. Adnan",
        "court_name": "High Court of Sindh",
        "decision_date": "2025-01-10"
    }
    res = StructuralJudgmentSegmenter.segment_judgment(SAMPLE_FAMILY_KHULA, metadata=meta)

    assert res["domain"] == "family"
    assert res["subdomain"] == "khula"
    assert "Family Courts Act, 1964" in res["statutes_cited"]
    assert "Muslim Family Laws Ordinance, 1961" in res["statutes_cited"]
    assert any("Section 10" in p for p in res["provisions_cited"])


def test_segment_banking_case():
    meta = {
        "case_id": "2026_CLD_292",
        "citation": "2026 CLD 292",
        "case_title": "Salman Capital v. HBL",
        "court_name": "Lahore High Court",
        "decision_date": "2026-02-05"
    }
    res = StructuralJudgmentSegmenter.segment_judgment(SAMPLE_BANKING_FIO, metadata=meta)

    assert res["domain"] == "banking_commercial"
    assert res["subdomain"] == "fio_recovery"
    assert "Financial Institutions (Recovery of Finances) Ordinance, 2001" in res["statutes_cited"]
    assert any("Section 9" in p or "Section 10" in p for p in res["provisions_cited"])
