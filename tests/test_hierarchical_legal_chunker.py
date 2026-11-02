"""
tests/test_hierarchical_legal_chunker.py

Unit Test Suite for Structure-Aware Hierarchical Legal Judgment Chunker.
Validates:
1. Explicit section heading parsing (Facts, Issues, Submissions, Analysis, Ratio, Order)
2. Implicit section detection across Pakistani judgment paragraphs (2006 YLR 2059)
3. Exact classification of Counsel Submissions (is_argument=True, is_holding=False)
4. Exact classification of Ratio Decidendi (section_type="ratio_decidendi", is_holding=True)
5. Section frontier containment (zero overlap bleed between arguments and holdings)
6. Paragraph boundary integrity and sentence-level fallback for oversized blocks
7. Metadata completeness for Pinecone dense vector upsert
"""

import pytest
from core.hierarchical_legal_chunker import (
    HierarchicalLegalChunker,
    SECTION_PREAMBLE,
    SECTION_HEADNOTE,
    SECTION_FACTS,
    SECTION_ISSUES,
    SECTION_ARGUMENTS,
    SECTION_ANALYSIS,
    SECTION_RATIO,
    SECTION_ORDER,
    count_tokens
)


SAMPLE_EXPLICIT_SECTIONS_JUDGMENT = """
2025 SCMR 100
[Supreme Court of Pakistan]
Present: Syed Mansoor Ali Shah, Athar Minallah, JJ
CIVIL APPEAL NO. 12-K OF 2024
Muhammad Ali --- Appellant
Versus
Federation of Pakistan --- Respondent
Mian Saqib Nisar, Senior ASC for Appellant.
Mansoor Usman Awan, Attorney General for Pakistan.

FACTS
Briefly stated, the facts leading to this appeal are that the appellant was serving as Director General in BPS-20. Through the impugned notification dated 12.01.2023, he was compulsorily retired from service on allegations of administrative irregularity. The appellant challenged the notification before the High Court in a constitutional petition under Article 199.

ISSUES FRAMED
The following questions arise for determination:
1. Whether an employee of a statutory authority governed by non-statutory service regulations can invoke constitutional jurisdiction under Article 199?
2. Whether the master and servant rule applies to autonomous regulatory bodies?

SUBMISSIONS OF COUNSEL
Learned counsel for the appellant contended that the impugned compulsory retirement order was issued in flagrant violation of natural justice and audi alteram partem. It was vehemently submitted that the employer authority was performing public functions and therefore amenability to Article 199 could not be bypassed.
On the other hand, the learned Attorney General argued that the service regulations of the authority were non-statutory. Learned State counsel contended that the relationship between the parties was strictly that of master and servant, rendering the writ petition non-maintainable.

JUDICIAL ANALYSIS
We have heard the learned counsel for the parties at length and examined the relevant statutory provisions and case law. It is profitable to refer to the constitutional trajectory of public employment in Pakistan. In order to appreciate the controversy, we must examine whether the terms of employment are grounded in a statute or purely contractual instruments.

RATIO DECIDENDI
We hold that where a statutory body exercises sovereign regulatory power, its internal service actions impacting tenure must conform to procedural fairness under Article 10A of the Constitution. It is a settled proposition of law that the master and servant rule cannot be deployed as a cloak to shield arbitrary or malafide dismissals by state instrumentalities. The question is answered in the affirmative.

OPERATIVE ORDER
For the reasons recorded above, this appeal is allowed. The impugned notification of compulsory retirement is declared illegal and set aside. Appellant shall be reinstated with all consequential back benefits. Order accordingly.
"""

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

SAMPLE_2024_PCRLJ_550 = """
2024 PCrLJ 550
[Lahore]
Before Ali Baqar Najafi, J
TARIQ MEHMOOD---Petitioner Versus THE STATE---Respondent
Criminal Miscellaneous No.12345-B of 2024, decided on 15th March, 2024.

Penal Code (XLV of 1860)---
----Ss. 406 & 420---Criminal breach of trust and cheating---Commercial dispute---Pre-arrest bail, grant of---FIR registered alleging failure to supply cotton bales after receiving advance payment---Held: Transaction between the parties arose out of an agreement to sell and commercial dealing---Non-performance of contractual promise does not per se constitute criminal offence of cheating under Section 420 PPC or criminal breach of trust under Section 406 PPC in absence of dishonest intention at inception---Criminal machinery cannot be activated as a recovery forum for civil debt---Petitioner has joined investigation and ad-interim pre-arrest bail is confirmed under Section 498 Cr.P.C.

ORDER

ALI BAQAR NAJAFI, J.--Through this petition under Section 498 Cr.P.C., petitioner Tariq Mehmood seeks pre-arrest bail in FIR No. 123 of 2024 registered under Sections 420 and 406 PPC at Police Station Civil Lines, Lahore.

2. Briefly stated, the prosecution story as narrated in the FIR is that complainant entered into a commercial transaction with petitioner for purchase of 500 cotton bales against payment of Rs. 5,000,000. It is alleged that petitioner received the amount but failed to deliver the goods.

3. Learned counsel for the petitioner contended that the dispute is purely civil in nature arising out of commercial transaction. Conversely, the learned Prosecutor General assisted by learned counsel for complainant vehemently argued that petitioner had fraudulent intention from the very inception and cheated the complainant.

4. We have heard the learned counsel for the parties and perused the record. A commercial transaction does not automatically transform into a penal offence. Non-performance of contractual promise does not per se constitute cheating under Section 420 PPC or criminal breach of trust under Section 406 PPC in absence of dishonest intention at inception. Criminal machinery cannot be activated as a recovery forum for civil debt.

5. In the foregoing circumstances, ad-interim pre-arrest bail is confirmed subject to furnishing fresh bail bonds. Petition allowed.
"""


SAMPLE_2026_SCMR_941 = """
Citation Name: 2026 SCMR 941 SUPREME-COURT
Bookmark this Case 

SHAHBAZ KHAN VS DOWLAT KHAN

O.XX, R.18 Partition of ancestral estate Family settlement Selective claim over disputed property by one heir Partial partition of property, permissibility of Preliminary decree Mandatory determination of shares Failure to specify shares Material irregularity Present matter concerned a dispute between three brothers over the partition of property left by their deceased father, comprising four houses. A preliminary decree was passed without specifying the shares of the parties. Held: The suit concerned the partition of property along with a request for separate possession of an individual share Given this context it was imperative that the Trial Court adhered to the procedural guidelines set out in Rule 18 of Order XX, C.P.C. when issuing preliminary decree Unfortunately, this essential procedure was overlooked Judgments and decrees rendered by the Courts below were unsustainable. Matter was referred back to the Trial Court to decide the suit afresh in accordance with law. Petition was converted into appeal and allowed.

O.XX, R.18 Suit for partial partition Maintainability Scope A party choosing to seek partition should not have the liberty to selectively choose and acquire a share in the more valuable aspects of the joint holdings while simultaneously excluding those portions of lesser value. Each co-owner possesses ownership rights over every inch of the joint holding corresponding to their share. Therefore, it is inappropriate for any part of the joint holding to be permitted for separate partition. Entire property corpus is aggregated into a common pool under Partition Act 1893.
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


def test_parse_explicit_sections():
    """Verifies that explicit heading markers correctly map to canonical section types."""
    sections = HierarchicalLegalChunker.parse_judgment_sections(SAMPLE_EXPLICIT_SECTIONS_JUDGMENT)
    sec_types = [s["section_type"] for s in sections]

    assert SECTION_FACTS in sec_types
    assert SECTION_ISSUES in sec_types
    assert SECTION_ARGUMENTS in sec_types
    assert SECTION_ANALYSIS in sec_types
    assert SECTION_RATIO in sec_types
    assert SECTION_ORDER in sec_types


def test_landmark_2006_ylr_2059_sections():
    """Verifies that 2006 YLR 2059 is decomposed into headnote, facts, arguments, ratio, and order."""
    sections = HierarchicalLegalChunker.parse_judgment_sections(SAMPLE_2006_YLR_2059)
    sec_types = [s["section_type"] for s in sections]

    # Headnote extracted from reporter summary
    assert SECTION_HEADNOTE in sec_types
    # Facts extracted from Paragraph 1
    assert SECTION_FACTS in sec_types
    # Ratio extracted from Paragraph 4 ("find that the same is not legally sustainable...")
    assert SECTION_RATIO in sec_types
    # Operative order extracted from Paragraph 5 ("Revision accepted")
    assert SECTION_ORDER in sec_types


def test_counsel_argument_isolation():
    """Verifies that counsel arguments are strictly flagged as is_argument=True and is_holding=False."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_EXPLICIT_SECTIONS_JUDGMENT,
        metadata={"case_id": "2025_SCMR_100", "citation": "2025 SCMR 100"}
    )

    arg_chunks = [c for c in chunks if c["section_type"] == SECTION_ARGUMENTS]
    assert len(arg_chunks) >= 1
    for ac in arg_chunks:
        assert ac["is_argument"] is True
        assert ac["is_holding"] is False
        assert "Learned counsel" in ac["text"] or "Attorney General" in ac["text"]


def test_ratio_decidendi_holding_tag():
    """Verifies that ratio decidendi chunks are strictly tagged is_holding=True and is_argument=False."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_EXPLICIT_SECTIONS_JUDGMENT,
        metadata={"case_id": "2025_SCMR_100", "citation": "2025 SCMR 100"}
    )

    ratio_chunks = [c for c in chunks if c["section_type"] == SECTION_RATIO]
    assert len(ratio_chunks) >= 1
    for rc in ratio_chunks:
        assert rc["is_holding"] is True
        assert rc["is_argument"] is False
        assert "We hold that" in rc["text"] or "settled proposition" in rc["text"]


def test_section_frontier_containment():
    """Verifies that a chunk never blends an argument and a ratio in the same text payload."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_EXPLICIT_SECTIONS_JUDGMENT,
        metadata={"case_id": "2025_SCMR_100", "citation": "2025 SCMR 100"}
    )

    for c in chunks:
        # A single chunk cannot be both an argument and a holding
        assert not (c["is_holding"] and c["is_argument"])


def test_paragraph_boundary_integrity():
    """Verifies that chunking does not cut mid-sentence or mid-paragraph for ordinary length paragraphs."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_2006_YLR_2059,
        metadata={"case_id": "2006_YLR_2059", "citation": "2006 YLR 2059"},
        target_tokens=512
    )

    # Every chunk clean_body should start and end with complete words/sentences
    for c in chunks:
        body = c["clean_body"]
        assert len(body) > 0
        assert not body.startswith(" ")
        assert not body.endswith(" ")


def test_oversized_paragraph_split_on_sentences():
    """Verifies that an oversized paragraph (> target_tokens) splits cleanly on sentence boundaries."""
    long_sentences = [
        f"This is legal principle sentence number {i} analyzing Section 12 of the Specific Relief Act 1877."
        for i in range(50)
    ]
    long_para = " ".join(long_sentences)
    judgment_text = f"JUDGMENT\n\nRATIO DECIDENDI\n\n{long_para}"

    chunks = HierarchicalLegalChunker.chunk_judgment(
        judgment_text,
        metadata={"case_id": "LONG_TEST", "citation": "2025 SCMR 999"},
        target_tokens=150  # Artificially low to trigger oversized paragraph split
    )

    assert len(chunks) > 1
    for c in chunks:
        # Every chunk should be bounded
        assert c["token_count"] <= 200
        # Should retain section type
        assert c["section_type"] == SECTION_RATIO
        assert c["is_holding"] is True


def test_criminal_420_bail_structure():
    """Verifies structural extraction on criminal Section 420 commercial dispute case."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_2024_PCRLJ_550,
        metadata={"case_id": "2024_PCrLJ_550", "citation": "2024 PCrLJ 550", "domain": "criminal"}
    )

    types = {c["section_type"] for c in chunks}
    assert SECTION_HEADNOTE in types or SECTION_RATIO in types
    assert SECTION_ORDER in types

    # Ratio chunk must identify the commercial dispute / dishonest intention rule
    holding_chunks = [c for c in chunks if c["is_holding"]]
    assert len(holding_chunks) >= 1
    holding_texts = " ".join(c["text"] for c in holding_chunks)
    assert "Section 420" in holding_texts
    assert "civil debt" in holding_texts or "commercial" in holding_texts


def test_pinecone_metadata_payload_schema():
    """Verifies that all chunk metadata fields conform to Pinecone vector schema."""
    meta_input = {
        "case_id": "2006_YLR_2059",
        "citation": "2006 YLR 2059",
        "case_title": "Khawaja Nayyar Qayyum v. Zubair Qayyum",
        "court_name": "Lahore High Court",
        "decision_date": "2006-01-01",
        "domain": "civil",
        "subdomain": "partition"
    }

    chunks = HierarchicalLegalChunker.chunk_judgment(SAMPLE_2006_YLR_2059, metadata=meta_input)

    for c in chunks:
        meta = c["metadata"]
        assert meta["case_id"] == "2006_YLR_2059"
        assert meta["citation"] == "2006 YLR 2059"
        assert meta["court"] == "Lahore High Court"
        assert meta["year"] == 2006
        assert meta["domain"] == "civil"
        assert meta["subdomain"] == "partition"
        assert "section_type" in meta
        assert "is_holding" in meta
        assert "is_argument" in meta
        assert "chunk_id" in meta
        assert meta["total_chunks"] == len(chunks)
        assert c["chunk_id"] == meta["chunk_id"]


def test_headnote_only_2026_scmr_941():
    """Verifies that headnote-only digest cases are tagged as headnote with is_holding=True."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_2026_SCMR_941,
        metadata={"case_id": "2026_SCMR_941", "citation": "2026 SCMR 941", "court": "Supreme Court of Pakistan"}
    )
    assert len(chunks) >= 1
    for c in chunks:
        assert c["is_holding"] is True
    assert any("Partition of ancestral estate" in c["text"] for c in chunks)
    assert any("partial partition" in c["text"] for c in chunks)


def test_family_khula_ratio_extraction():
    """Verifies Khula decree statutory mandate and Khurshid Bibi rule tagged as holding."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_FAMILY_KHULA,
        metadata={"case_id": "2025_CLC_120", "citation": "2025 CLC 120", "domain": "family"}
    )
    assert len(chunks) >= 1
    holding_chunks = [c for c in chunks if c["is_holding"]]
    assert len(holding_chunks) >= 1
    all_text = " ".join(c["text"] for c in holding_chunks)
    assert "Section 10(4)" in all_text
    assert "Consent of husband" in all_text or "mandatory statutory duty" in all_text


def test_banking_fio_ratio_extraction():
    """Verifies banking FIO 2001 Section 10 leave to defend ratio tagged as holding."""
    chunks = HierarchicalLegalChunker.chunk_judgment(
        SAMPLE_BANKING_FIO,
        metadata={"case_id": "2026_CLD_292", "citation": "2026 CLD 292", "domain": "banking_commercial"}
    )
    assert len(chunks) >= 1
    holding_chunks = [c for c in chunks if c["is_holding"]]
    assert len(holding_chunks) >= 1
    all_text = " ".join(c["text"] for c in holding_chunks)
    assert "Section 10" in all_text
    assert "leave to defend" in all_text


def test_clean_portal_debris():
    """Verifies stripping of navigation banners and portal scraping noise."""
    dirty_text = "Citation Name: 2026 SCMR 100\nBookmark this Case\nHelp FAQs Sitemap\nPage 1 of 5\n\nJUDGMENT\n\n1. Real text."
    cleaned = HierarchicalLegalChunker.clean_portal_debris(dirty_text)
    assert "Bookmark this Case" not in cleaned
    assert "Help FAQs" not in cleaned
    assert "Page 1 of 5" not in cleaned
    assert "Real text." in cleaned


def test_batch_vector_indexer_integration():
    """Verifies that batch_vector_indexer.chunk_judgment_text delegates to hierarchical chunker."""
    from scripts.batch_vector_indexer import chunk_judgment_text

    chunks = chunk_judgment_text(
        text=SAMPLE_EXPLICIT_SECTIONS_JUDGMENT,
        citation="2025 SCMR 100",
        title="Muhammad Ali v. Federation",
        court="Supreme Court of Pakistan",
        year="2025",
        case_id="2025_SCMR_100",
        use_hierarchical=True
    )
    assert len(chunks) >= 1
    # Test Gate: Chunks containing the holding are tagged ratio_decidendi
    ratio_chunks = [c for c in chunks if c.get("section_type") == "ratio_decidendi"]
    assert len(ratio_chunks) >= 1
    for rc in ratio_chunks:
        assert rc["is_holding"] is True
        assert rc["metadata"]["section_type"] == "ratio_decidendi"

    # Test backward compatibility sliding-window mode
    legacy_chunks = chunk_judgment_text(
        text=SAMPLE_EXPLICIT_SECTIONS_JUDGMENT,
        citation="2025 SCMR 100",
        title="Muhammad Ali v. Federation",
        use_hierarchical=False
    )
    assert len(legacy_chunks) >= 1
    assert isinstance(legacy_chunks[0], tuple)
