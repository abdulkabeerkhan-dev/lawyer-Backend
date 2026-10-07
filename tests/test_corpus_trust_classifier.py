# tests/test_corpus_trust_classifier.py
"""
Unit and Integration Tests for Mission 1 & 1.1 Corpus Trust Classifier
Verifies deterministic categorization across all controlled vocabularies and gold regression fixtures:
- known reciprocal swap
- known shifted sequence
- known wrong-title/right-text
- known displaced-text
- known page-slip-only
- known listing table
"""

import unittest
from scripts.classify_corpus_trust import classify_record_trust, CLASSIFIER_VERSION


class TestCorpusTrustClassifier(unittest.TestCase):

    def test_authentic_clean_judgment_trusted(self):
        """Authentic superior court judgment with matching citation and party header."""
        rec = {
            "case_id": "1958_PLD_SC_533",
            "case_title": "State v. Dosso",
            "neutral_citation": "PLD 1958 SC 533",
            "court_name": "Supreme Court of Pakistan",
            "decision_date": "1958-10-14",
            "source_url": "https://pakistancode.gov.pk/judgments/1958_PLD_SC_533",
            "full_text": (
                "PLD 1958 Supreme Court 533\n"
                "Present: Muhammad Munir, C.J., Shahabuddin, Cornelius and Rahman, JJ.\n"
                "THE STATE - Appellant versus DOSSO and another - Respondents\n"
                "Criminal Appeals Nos. 25, 26, 27 and 28 of 1958, decided on 14th October 1958.\n"
                "Constitution of Pakistan (1956), Art. 4 -- Laws (Continuance in Force) Order, 1958.\n"
                "The Chief Justice delivered the following judgment of the Court..."
            )
        }
        res = classify_record_trust(rec)
        self.assertEqual(res["retrieval_status"], "trusted")
        self.assertEqual(res["citation_status"], "verified")
        self.assertEqual(res["identity_status"], "verified")
        self.assertEqual(res["title_status"], "verified")
        self.assertEqual(res["provenance_status"], "verified")
        self.assertIn(res["content_quality"], ("full_text", "mixed", "headnote_only", "order_text"))

    def test_scraped_portal_chrome_rejected(self):
        """Scraped website navigation boilerplate or Latest Caselaws rejected."""
        rec = {
            "case_id": "2020_PCRLJ_100",
            "case_title": "Portal Chrome Stub",
            "neutral_citation": "2020 PCRLJ 100",
            "full_text": (
                "Latest Caselaws from the Journal Section\n"
                "My Account Feedback Bookmark this Case\n"
                "Oratier Technologies Pvt Ltd Customer Care Office"
            )
        }
        res = classify_record_trust(rec)
        self.assertEqual(res["retrieval_status"], "rejected")
        self.assertIn(res["content_quality"], ("portal_chrome", "stub"))

    def test_sync_placeholder_stub_rejected(self):
        """Placeholder undergoing index synchronization rejected as stub."""
        rec = {
            "case_id": "2023_SCMR_50",
            "case_title": "Precedent Record",
            "neutral_citation": "2023 SCMR 50",
            "full_text": "Full judgment record for 2023 SCMR 50 is currently undergoing index synchronization."
        }
        res = classify_record_trust(rec)
        self.assertEqual(res["retrieval_status"], "rejected")
        self.assertEqual(res["content_quality"], "stub")

    def test_repairable_title_restricted(self):
        """Truncated or placeholder title where header parties exist is repairable and restricted."""
        rec = {
            "case_id": "2019_SCMR_800",
            "case_title": "Civil Petition No. 55 of 2018...",
            "neutral_citation": "2019 SCMR 800",
            "full_text": (
                "2019 S C M R 800\n"
                "Present: Asif Saeed Khan Khosa, C.J. and Syed Mansoor Ali Shah, J\n"
                "TARIQ MEHMOOD - Appellant versus THE STATE - Respondent\n"
                "Criminal Appeal No. 44 of 2018, decided on 12th March 2019.\n"
                "Pakistan Penal Code (XLV of 1860), S. 302(b)..."
            )
        }
        res = classify_record_trust(rec)
        self.assertEqual(res["retrieval_status"], "restricted")
        self.assertEqual(res["title_status"], "repairable")
        self.assertEqual(res["header_parties"], "TARIQ MEHMOOD v. THE STATE")

    # =========================================================================
    # GOLD REGRESSION FIXTURES (Historical Defect Cases)
    # =========================================================================

    def test_known_reciprocal_swap_fixture(self):
        """
        Gold Fixture: 2005 PLD QTA 1 <-> 2005 CLC 1241 reciprocal swap.
        Case A holds Case B's text/parties and Case B holds Case A's text/parties.
        Classifier MUST quarantine both as displaced case identities.
        """
        # Case A: 2005_PLD_QTA_1 holds text of 2005 CLC 1241
        case_a = {
            "case_id": "2005_PLD_QTA_1",
            "case_title": "ASHFAQ KHALID VS THE STATE",
            "neutral_citation": "PLD 2005 SC 1",
            "full_text": (
                "2005 C L C 1241\n"
                "[Quetta]\n"
                "Before Amanullah Khan, J\n"
                "Haji JAN MUHAMMAD - Petitioner versus Mst. ANWARI HUSSAIN - Respondent\n"
                "Civil Revision No. 200 of 2004, decided on 10th December 2004.\n"
                "Specific Relief Act (I of 1877), S. 42..."
            )
        }
        res_a = classify_record_trust(case_a)
        self.assertEqual(res_a["retrieval_status"], "quarantined")
        self.assertEqual(res_a["citation_status"], "mismatch")
        self.assertEqual(res_a["identity_status"], "conflict")
        self.assertEqual(res_a["title_status"], "contradictory")
        self.assertIn("Displaced case identity", res_a["verification_reason"])

        # Case B: 2005_CLC_1241 holds text of 2005 PLD 1 Quetta
        case_b = {
            "case_id": "2005_CLC_1241",
            "case_title": "Haji JAN MUHAMMAD VS Mst. ANWARI HUSSAIN",
            "neutral_citation": "2005 CLC 1241",
            "full_text": (
                "Citation Name: 2005 PLD 1 QUETTA-HIGH-COURT-BALOCHISTAN\n"
                "ASHFAQ KHALID VS THE STATE\n"
                "Before Amanullah Khan, J\n"
                "Criminal Bail Application No. 50 of 2004, decided on 5th January 2005.\n"
                "Control of Narcotic Substances Act (XXV of 1997), S. 9(c)..."
            )
        }
        res_b = classify_record_trust(case_b)
        self.assertEqual(res_b["retrieval_status"], "quarantined")
        self.assertEqual(res_b["citation_status"], "mismatch")
        self.assertEqual(res_b["identity_status"], "conflict")
        self.assertEqual(res_b["title_status"], "contradictory")
        self.assertIn("Displaced case identity", res_b["verification_reason"])

    def test_known_shifted_sequence_fixture(self):
        """
        Gold Fixture: Systematic contiguous offset / sequence displacement.
        Record N metadata (1992 CLC 100) contains internal text header belonging to N-1 (1992 CLC 99).
        Classifier MUST quarantine as displaced text.
        """
        shifted_record = {
            "case_id": "1992_CLC_100",
            "case_title": "Ahmed Khan v. Bashir Ahmed",
            "neutral_citation": "1992 CLC 100",
            "full_text": (
                "1992 C L C 99\n"
                "[Lahore]\n"
                "Before Khalil-ur-Rehman Khan, J\n"
                "ZAHID HUSSAIN - Appellant versus TARIQ MEHMOOD - Respondent\n"
                "First Appeal from Order No. 45 of 1991, decided on 12th November 1991.\n"
                "Civil Procedure Code (V of 1908), O. XXXIX, Rr. 1 & 2..."
            )
        }
        res = classify_record_trust(shifted_record)
        self.assertEqual(res["retrieval_status"], "quarantined")
        self.assertEqual(res["citation_status"], "mismatch")
        self.assertEqual(res["identity_status"], "conflict")
        self.assertEqual(res["title_status"], "contradictory")

    def test_known_wrong_title_right_text_fixture(self):
        """
        Gold Fixture: Mode (c) Defect.
        Contradictory title (e.g. statutory clause in title), but text and citation belong to the case.
        Classifier MUST classify as RESTRICTED (not quarantined), preserving text for metadata repair.
        """
        rec = {
            "case_id": "2021_SCMR_500",
            "case_title": "Wrongly Indexed Company Name Ltd v. Federation",
            "neutral_citation": "2021 SCMR 500",
            "full_text": (
                "2021 S C M R 500\n"
                "Present: Umar Ata Bandial, Mazhar Alam Khan Miankhel and Qazi Muhammad Amin Ahmed, JJ\n"
                "MUHAMMAD ARIF - Petitioner versus MST. BASHIRAN BIBI - Respondent\n"
                "Civil Petition No. 123 of 2020, decided on 10th February 2021.\n"
                "Specific Relief Act (I of 1877), S. 42 -- Suit for declaration regarding inheritance..."
            )
        }
        res = classify_record_trust(rec)
        self.assertEqual(res["retrieval_status"], "restricted")
        self.assertEqual(res["citation_status"], "verified")
        self.assertEqual(res["title_status"], "contradictory")
        self.assertIn("Contradictory title on verified judgment text", res["verification_reason"])

    def test_known_displaced_text_fixture(self):
        """
        Gold Fixture: Unilateral text displacement from another court or year.
        Metadata claims 1991 SCMR 1764 (Supreme Court), but text body is 1975 PCrLJ 123 (High Court).
        Classifier MUST quarantine.
        """
        displaced_rec = {
            "case_id": "1991_SCMR_1764_DISPLACED",
            "case_title": "Federal Government v. Public at Large",
            "neutral_citation": "1991 SCMR 1764",
            "full_text": (
                "1975 PCrLJ 123\n"
                "[Karachi]\n"
                "Before Tufail Ali A. Rahman, C.J.\n"
                "GHULAM MUHAMMAD - Applicant versus THE STATE - Respondent\n"
                "Criminal Revision No. 12 of 1974, decided on 15th August 1974.\n"
                "Criminal Procedure Code (V of 1898), S. 497..."
            )
        }
        res = classify_record_trust(displaced_rec)
        self.assertEqual(res["retrieval_status"], "quarantined")
        self.assertEqual(res["citation_status"], "mismatch")
        self.assertEqual(res["identity_status"], "conflict")

    def test_known_page_slip_only_fixture(self):
        """
        Gold Fixture: Real-world page mismatch (1969 PLD 274 vs 374).
        Parties match, but printed page number differs (374 vs 274).
        Classifier detects citation mismatch and isolates record from generation.
        """
        page_slip_rec = {
            "case_id": "1969_PLD_274",
            "case_title": "Bashir Ahmad v. The State",
            "neutral_citation": "1969 PLD 274",
            "full_text": (
                "PLD 1969 Lahore 374\n"
                "Before Muhammad Afzal Cheema, J\n"
                "BASHIR AHMAD - Appellant versus THE STATE - Respondent\n"
                "Criminal Appeal No. 120 of 1968, decided on 15th January 1969.\n"
                "Pakistan Penal Code (XLV of 1860), S. 302..."
            )
        }
        res = classify_record_trust(page_slip_rec)
        self.assertEqual(res["retrieval_status"], "restricted")
        self.assertEqual(res["citation_status"], "mismatch")
        self.assertEqual(res["identity_status"], "verified")  # Parties match!
        self.assertEqual(res["title_status"], "verified")
        self.assertIn("Page/citation mismatch on verified identity", res["verification_reason"])

    def test_known_listing_table_fixture(self):
        """
        Gold Fixture: Scraped volume digest index table starting with '# Citation Title Court'.
        Classifier MUST reject with content_quality = 'listing_table'.
        """
        listing_rec = {
            "case_id": "2024_PLD_INDEX_1",
            "case_title": "Volume Index",
            "neutral_citation": "2024 PLD 1",
            "full_text": (
                "# Citation Title Court Read\n"
                "PLD 2024 SC 1 Title 1 Read\n"
                "PLD 2024 SC 15 Title 2 Read\n"
                "PLD 2024 SC 30 Title 3 Read"
            )
        }
        res = classify_record_trust(listing_rec)
        self.assertEqual(res["retrieval_status"], "rejected")
        self.assertEqual(res["content_quality"], "listing_table")


if __name__ == "__main__":
    unittest.main()
