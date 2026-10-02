"""
Regression test suite for Companies Act 2017 minority shareholder & winding up query.
Tests the 8 remediation criteria:
1. Bare section citations & unknown statutes do not default to CPC_1908.
2. Contextual statutory detection carries forward Act across clauses (Section 301 -> Companies Act 2017).
3. Non-baseline acts return '[NOT CHECKED: statute not in tables]'.
4. Caption-only records (e.g. Haji Muhammad Ismail 2002 PLD SC 510) classified as caption_only.
5. Quote sanitization preserves whitespace without word agglutination.
6. Fail-closed citation grounding preserves paragraph structure and markdown headings.
7. Domain whitelist includes caselaw.shc.gov.pk.
"""

import unittest
from core.statutory_validator import parse_statutory_citation, validate_statutory_citation
from core.statute_currency import check_statute_currency, detect_statutory_provisions_in_query
from core.legal_guardrails import (
    classify_judgment_structure,
    is_caption_only_record,
    sanitize_unverified_quotes,
    fail_closed_citation_grounding
)
from core.domain_whitelist import is_whitelisted_court_url, derive_court_from_url


class TestCompaniesActMinorityQuery(unittest.TestCase):

    def test_bare_section_no_cpc_fallback(self):
        """Sections > 158 must never default to CPC_1908."""
        parsed_286 = parse_statutory_citation("Section 286")
        self.assertIsNotNone(parsed_286)
        self.assertIsNone(parsed_286.get("act_code"))
        self.assertFalse(parsed_286.get("explicit_act"))

        parsed_301 = parse_statutory_citation("Section 301")
        self.assertIsNotNone(parsed_301)
        self.assertIsNone(parsed_301.get("act_code"))
        self.assertFalse(parsed_301.get("explicit_act"))

        # Bare section validation must NEVER default to CPC_1908 for sections > 158
        val_bare = validate_statutory_citation("Section 286")
        self.assertNotEqual(val_bare.get("canonical_id"), "CPC_1908_SEC_286")
        self.assertNotEqual(val_bare.get("act_code"), "CPC_1908")

        val_nonexistent = validate_statutory_citation("Section 999")
        self.assertFalse(val_nonexistent.get("is_valid"))
        self.assertEqual(val_nonexistent.get("status"), "missing_act")

        # Explicit Companies Act citation returns statute_not_in_tables
        val_res = validate_statutory_citation("Section 286 of the Companies Act, 2017")
        self.assertFalse(val_res.get("is_valid"))
        self.assertEqual(val_res.get("status"), "statute_not_in_tables")
        self.assertEqual(val_res.get("canonical_id"), "COMPANIES_ACT_2017_SEC_286")

    def test_query_provision_detection(self):
        """Query with Section 286 of Companies Act, 2017 and (Section 301) detects both properly."""
        query = (
            "A group of minority shareholders holding 12% of the issued paid-up capital of a "
            "private limited company filed a petition before the High Court (Company Bench) under "
            "Section 286 of the Companies Act, 2017, alleging severe oppression, mismanagement, "
            "and siphoning of company assets by the majority directors. In the same petition, they prayed "
            "for the immediate winding up of the company under the just and equitable clause (Section 301)."
        )
        provisions = detect_statutory_provisions_in_query(query)
        prov_map = dict(provisions)

        self.assertIn("COMPANIES_ACT_2017_SEC_286", prov_map)
        self.assertEqual(prov_map["COMPANIES_ACT_2017_SEC_286"], "COMPANIES_ACT_2017")

        self.assertIn("COMPANIES_ACT_2017_SEC_301", prov_map)
        self.assertEqual(prov_map["COMPANIES_ACT_2017_SEC_301"], "COMPANIES_ACT_2017")

        # Must NOT contain CPC_1908_SEC_286 or CPC_1908_SEC_301
        self.assertNotIn("CPC_1908_SEC_286", prov_map)
        self.assertNotIn("CPC_1908_SEC_301", prov_map)

    def test_statute_currency_not_in_tables(self):
        """Unknown statute tables return '[NOT CHECKED: statute not in tables]'."""
        res_286 = check_statute_currency("COMPANIES_ACT_2017_SEC_286", "COMPANIES_ACT_2017")
        self.assertEqual(res_286.get("display_tag"), "[NOT CHECKED: statute not in tables]")
        self.assertEqual(res_286.get("status"), "not_in_tables")

        res_301 = check_statute_currency("COMPANIES_ACT_2017_SEC_301", "COMPANIES_ACT_2017")
        self.assertEqual(res_301.get("display_tag"), "[NOT CHECKED: statute not in tables]")
        self.assertEqual(res_301.get("status"), "not_in_tables")

    def test_caption_only_detection(self):
        """Haji Muhammad Ismail 2002 PLD SC 510 record with only caption metadata is caption_only."""
        haji_text = (
            "2002 PLD 510 SUPREME-COURT\n"
            "Present: Muhammad Bashir Jehangiri, C.J., Nazim Hussain Siddiqui and Tanvir Ahmed Khan, JJ\n"
            "Civil Appeal No. 719 of 1999\n"
            "HAJI MUHAMMAD ISMAIL & CO.---Appellant\n"
            "versus\n"
            "PAKISTAN---Respondent\n"
            "Decided on 28-3-2002."
        )
        self.assertTrue(is_caption_only_record(haji_text))
        classification = classify_judgment_structure(haji_text)
        self.assertEqual(classification.get("detected_type"), "caption_only")

    def test_substantive_judgment_not_caption_only(self):
        """A full judgment or substantive headnote is NOT caption_only."""
        substantive_text = (
            "2020 SCMR 123\n"
            "Present: Gulzar Ahmed, C.J.\n"
            "It is well settled that winding up of a running commercial enterprise is a remedy of last resort. "
            "The Company Judge must explore all viable alternative remedies under Section 286 before considering "
            "the severe drastic order of winding up under the just and equitable clause. "
            "Where the substratum of the company is fully intact and profitable, mere differences between "
            "majority and minority shareholders do not warrant liquidation."
        )
        self.assertFalse(is_caption_only_record(substantive_text))
        classification = classify_judgment_structure(substantive_text)
        self.assertNotEqual(classification.get("detected_type"), "caption_only")

    def test_quote_sanitization_preserves_whitespace(self):
        """Stripping unverified quotes must not agglutinate adjacent words."""
        original = 'The court applied the "The Substratum Intact Test" in determining the petition.'
        sanitized = sanitize_unverified_quotes(original, ["The Substratum Intact Test"])
        self.assertIn("The Substratum Intact Test", sanitized)
        self.assertNotIn("TheSubstratum", sanitized)
        self.assertNotIn("IntactTest", sanitized)

        text2 = 'Allegations of "mismanagement" and "oppression" vs. winding up.'
        sanitized2 = sanitize_unverified_quotes(text2, ["mismanagement", "oppression"])
        self.assertIn("of mismanagement", sanitized2)
        self.assertIn("oppression vs", sanitized2)
        self.assertNotIn("ofmismanagement", sanitized2)
        self.assertNotIn("Oppressionvs", sanitized2)

    def test_paragraph_preservation_in_fail_closed_grounding(self):
        """Markdown headings and paragraph boundaries must not be collapsed into a single wall of text."""
        memo = (
            "### I. EXECUTIVE SUMMARY & LEGAL OPINION\n\n"
            "Winding up is strictly a remedy of last resort.\n\n"
            "---\n\n"
            "### II. CONTROLLING STATUTORY ARCHITECTURE\n\n"
            "Sections 286 and 301 of the Companies Act govern shareholder remedies."
        )
        # With empty retrieved cases, grounding should retain structural headings and double newlines
        processed, _, _ = fail_closed_citation_grounding(memo, [])
        self.assertIn("### I. EXECUTIVE SUMMARY & LEGAL OPINION", processed)
        self.assertIn("### II. CONTROLLING STATUTORY ARCHITECTURE", processed)
        self.assertIn("\n\n", processed)

    def test_caselaw_shc_domain_whitelist(self):
        """caselaw.shc.gov.pk is recognized as a whitelisted court repository."""
        self.assertTrue(is_whitelisted_court_url("https://caselaw.shc.gov.pk/caselaw/view-file/12345"))
        self.assertEqual(derive_court_from_url("https://caselaw.shc.gov.pk/view"), "High Court of Sindh")


if __name__ == "__main__":
    unittest.main()
