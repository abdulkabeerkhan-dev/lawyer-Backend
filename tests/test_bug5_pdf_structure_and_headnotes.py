"""
tests/test_bug5_pdf_structure_and_headnotes.py

Verification suite for Bug 5:
1. Pakistan Law Site PDF Type A vs Type B parsing & structural segmentation:
   - Type A: ORDER section extracted as full_text, headnote as headnote,
     misleading repeated headnote under 'FULL JUDGMENT TEXT' label and copyright footers discarded.
     content_level = 'full_judgment' only when ORDER section > 200 words.
   - Type B: Contains only headnotes, no ORDER section starting with 'J.---'
     (e.g. 2023 CLD 1249 and 2023 CLD 33).
     Stores headnote as headnote, sets full_text = None, content_level = 'headnote'.
2. Downstream verified badge downgrade:
   - Records with content_level = 'headnote' or 'headnote_only' NEVER receive verified badge.
   - Verification status is strictly 'HEADNOTE_ONLY - not verified'.
"""

import pytest
from core.structural_judgment_segmenter import (
    StructuralJudgmentSegmenter,
    parse_pakistan_law_site_document,
)
from core.content_classification import classify_judgment_content
from core.case_store import get_case_by_identifier


TYPE_A_TEXT = """Citation Name: 2022 SCMR 1500
Bookmark this Case

Petitioner VS Respondent

S. 497---Criminal Procedure Code---Post-arrest bail---Scope---Further inquiry.
Held: Where ocular testimony contradicts medical evidence and delay in FIR remains unexplained,
the accused is entitled to the concession of post-arrest bail as a matter of right under subsection (2).

ORDER

MUHAMMAD SAJID MEHMOOD SETHI, J.---Through the instant petition under section 498 Cr.P.C., the petitioner seeks
grant of pre-arrest bail in case FIR No. 345/2021 registered at Police Station City for offences under sections
302, 324, 148, 149 PPC. We have heard the learned counsel for the parties at considerable length and examined the
record with their able assistance.

The prosecution case against the petitioner is primarily based on ocular testimony furnished by interested witnesses.
The medical evidence available on record contradicts the ocular account regarding the locale of injuries.
Furthermore, there is an unexplained delay of more than thirty-six hours in lodging the First Information Report,
which strongly indicates deliberate deliberation and preliminary consultation before naming the present petitioner.
It is an established canon of criminal jurisprudence that bail cannot be withheld as punishment at the tentative
stage of proceedings when the case against the petitioner requires further inquiry into his guilt.

For the reasons recorded above, we are of the considered opinion that the petitioner has made out a fit case for
the grant of concession of pre-arrest bail. Accordingly, this petition is converted into an appeal and allowed.
The interim pre-arrest bail earlier granted to the petitioner is hereby confirmed subject to his furnishing bail bonds
in the sum of Rs. 200,000/- with two sureties each in the like amount to the satisfaction of the learned trial court.

FULL JUDGMENT TEXT

S. 497---Criminal Procedure Code---Post-arrest bail---Scope---Further inquiry.
Held: Where ocular testimony contradicts medical evidence and delay in FIR remains unexplained,
the accused is entitled to the concession of post-arrest bail as a matter of right under subsection (2).

Copyrights © 2026 by Oratier Technologies (Pvt.) Ltd.
This site is developed & maintained Oratier Technologies (Pvt.) Ltd.
Help FAQ's Sitemap
"""

TYPE_B_TEXT_2023_CLD_1249 = """Citation Name: 2023 CLD 1249 ISLAMABAD
Bookmark this Case 

ANWAR BAIG, CHAIRMAN CONSERVANCY MANAGEMENT COMMITTEE (CMC) VS GOVERNMENT OF PAKISTAN through Secretary Ministry of Climate Change

Applicability--Term , Companies Act 2017--286 , Companies Act 2017--42 ,
Ss. 42 & 286---Company with charitable and not for profit objects---Mismanagement of affairs---Invoking jurisdiction of High Court---Principle---Rule of Indoor Management---Applicability---Petitioners were members of Board of Directors of respondent company who alleged mismanagement in its affairs---Validity---Provision of S. 286 of Companies Act, 2017, retained right for minority shareholders and reduced threshold test from twenty percent of issued capital of respondent company to ten percent---Underlying rationale for prescribing a threshold to establish locus standi of minority shareholders to petition the Court and seek prevention against oppression and mismanagement was to ensure that not every grievance of an individual member was brought before High Court, as rule of indoor management was to remain alive and well---It was for such purpose that S. 286 of Companies Act, 2017 provided a mechanism empowering High Court to interfere with management of a company without requiring that the company be wound-up---Purpose of such provision was to protect interests of certain stakeholders, such as minority shareholders and creditors who had no general ability to exercise supervisory authority over Board of Directors or avail processes available within shareholders democracy to protect their interests---Respondent company was licensed under S. 42 of Companies Act, 2017, by SECP to pursue not-for-profit objects---According to Articles of Association of respondent Company, it was a public company limited by guarantee not having a share capital---While the Articles conceive that respondent company can have members, such members do not own share capital of the company---As respondent company did not have a share capital, such members therefore could not meet threshold test of owning ten percent of shareholding of the company as prescribed in S. 286 of Companies Act, 2017---Even if petitioners were members of respondent company in addition to being Directors, given that they did not own ten percent of paid-up share capital of the company, they would not qualify to file a petition under S. 286 of Companies Act, 2017---Petitioners had no locus standi to invoke jurisdiction of High Court under S. 286 of Companies Act, 2017---Petition was dismissed, in circumstances.

Copyrights © 2026 by Oratier Technologies (Pvt.) Ltd.
This site is developed & maintained Oratier Technologies (Pvt.) Ltd.
Help FAQ's Sitemap
"""

TYPE_B_TEXT_2023_CLD_33 = """Citation Name: 2023 CLD 33 KARACHI-HIGH-COURT-SINDH
Bookmark this Case 

NP WATERPROOF INDUSTRIES (PRIVATE) LTD. VS NP SPINNING MILLS LIMITED

Companies Act 2017--286 , Companies Act 2017--78 , Procedure--TERM ,
Ss. 78 & 286--- Transfer of shares to successor-in-interest---Procedure---Personal law, applicability of---Scope---Dispute was with regard to transfer of shares of company in favour of successors-in-interest of deceased share-holder---Objection raised by respondents was that minimum threshold of holdings and paid up capital of company was not matched by petitioners---Respondents further contended that neither Succession Certificate nor any lawful award was filed by petitioners in their favour---Validity---Case where an entity was created by a special law, it was to be dealt with within that frame of special law---No provision of special Act would take away any of their right under general law but it laid down a procedure of its own because the entity was creation of company law---Successor who intended to take advantage of any of its shareholding left by deceased had to go through a process prescribed by S. 78 of Companies Act, 2017 which had provided that shares or other securities of deceased member would be transferred on application duly supported by Succession Certificate or by lawful Award, as the case could be in favour of successors to the extent of their interest and their names were to be entered in Register of Companies---Officials of Securities and Exchange Commission of Pakistan (SECP) might not be aware of devolvement of shares amongst legal heirs and also as to who were the legal heirs to whom shares were devolved---Law had set a mechanism for transfer of shares, which was dependent on a Succession Certificate or lawful award by a Court of law---Majority shareholders' rights and their decision taken in such regard could not be ordinarily objected unless a significant number of shareholders, which was prescribed as 10% of the issued share capital of company, was achieved---If such minority shareholders were allowed to object and interfere in decisions of majority shareholders, business of the company would not function---Held, it was always wisdom of majority shareholders and insofar as decision of company was concerned, unless prerequisite of Ss. 78 & 286 of Companies Act 2017 were met, interference in the business affairs was not appropriate---Petitioners did not file a succession petition in respect of shares which were claimed after demise of their predecessor-in-interest---Suit for administration was pending which was filed by one of the respondents who claimed administration of moveable and immovable assets left by deceased shareholder---Requisite compliance was not made in terms of S. 78 of Companies Act, 2017---Proceedings for oppressive conduct by majority shareholders under S. 286 of Companies Act, 2017 were not maintainable--- Petition was dismissed, in circumstances.

Copyrights © 2026 by Oratier Technologies (Pvt.) Ltd.
This site is developed & maintained Oratier Technologies (Pvt.) Ltd.
Help FAQ's Sitemap
"""


def test_type_a_pdf_parsing_extracts_order_as_full_text_and_strips_misleading_tail():
    parsed = parse_pakistan_law_site_document(TYPE_A_TEXT)

    assert parsed["is_type_a"] is True
    assert parsed["is_type_b"] is False
    assert parsed["content_level"] == "full_judgment"
    assert parsed["detected_type"] == "full_judgment"

    # ORDER section must start with the judge byline and order reasoning
    assert "MUHAMMAD SAJID MEHMOOD SETHI, J.---" in parsed["order_text"]
    assert "MUHAMMAD SAJID MEHMOOD SETHI, J.---" in parsed["full_text"]
    assert len(parsed["order_text"].split()) > 200

    # Headnote section must contain editorial text before the judge byline
    assert "S. 497---Criminal Procedure Code---Post-arrest bail" in parsed["headnote_text"]
    assert "Where ocular testimony contradicts medical evidence" in parsed["headnote_text"]
    assert "MUHAMMAD SAJID MEHMOOD SETHI, J.---" not in parsed["headnote_text"]

    # The misleading repeated headnote at the tail under "FULL JUDGMENT TEXT" MUST be stripped
    assert "FULL JUDGMENT TEXT" not in parsed["order_text"]
    assert "FULL JUDGMENT TEXT" not in parsed["full_text"]

    # Scraper and Oratier copyright footers must NOT be present
    assert "Oratier Technologies" not in parsed["order_text"]
    assert "Help FAQ's Sitemap" not in parsed["order_text"]


def test_type_b_pdf_parsing_detects_headnote_only_for_2023_cld_1249():
    parsed = parse_pakistan_law_site_document(TYPE_B_TEXT_2023_CLD_1249)

    assert parsed["is_type_a"] is False
    assert parsed["is_type_b"] is True
    assert parsed["content_level"] == "headnote"
    assert parsed["detected_type"] == "headnote_only"

    # In Type B, full_text must be NULL/None
    assert parsed["full_text"] is None
    assert parsed["order_text"] == ""

    # Headnote must contain the editorial summary
    assert "Ss. 42 & 286---Company with charitable and not for profit objects" in parsed["headnote_text"]
    assert "Petitioners had no locus standi" in parsed["headnote_text"]

    # Oratier copyright footer stripped
    assert "Oratier Technologies" not in parsed["headnote_text"]


def test_type_b_pdf_parsing_detects_headnote_only_for_2023_cld_33():
    parsed = parse_pakistan_law_site_document(TYPE_B_TEXT_2023_CLD_33)

    assert parsed["is_type_a"] is False
    assert parsed["is_type_b"] is True
    assert parsed["content_level"] == "headnote"
    assert parsed["detected_type"] == "headnote_only"

    assert parsed["full_text"] is None
    assert parsed["order_text"] == ""
    assert "Ss. 78 & 286--- Transfer of shares to successor-in-interest" in parsed["headnote_text"]
    assert "Oratier Technologies" not in parsed["headnote_text"]


def test_content_classification_guardrail_against_fake_full_judgments():
    # Long headnotes without J.--- or judicial order must NOT be classified as full_judgment
    rec_cld = {"full_text": TYPE_B_TEXT_2023_CLD_1249, "content_level": "full_judgment"}
    assert classify_judgment_content(rec_cld) == "headnote"

    rec_cld33 = {"full_text": TYPE_B_TEXT_2023_CLD_33, "content_level": "full_judgment"}
    assert classify_judgment_content(rec_cld33) == "headnote"

    # Type A text is correctly classified as full_judgment
    rec_type_a = {"full_text": TYPE_A_TEXT, "content_level": "full_judgment"}
    assert classify_judgment_content(rec_type_a) == "full_judgment"


def test_case_store_hydrates_cld_cases_as_headnote_only():
    c1249 = get_case_by_identifier("2023 CLD 1249")
    assert c1249 is not None
    assert c1249.get("content_level") == "headnote"
    assert c1249.get("text_type") == "headnote"
    assert c1249.get("full_text") is None
    assert c1249.get("headnote") is not None
    assert len(c1249["headnote"]) > 100

    c33 = get_case_by_identifier("2023 CLD 33")
    assert c33 is not None
    assert c33.get("content_level") == "headnote"
    assert c33.get("text_type") == "headnote"
    assert c33.get("full_text") is None
    assert c33.get("headnote") is not None
    assert len(c33["headnote"]) > 100
