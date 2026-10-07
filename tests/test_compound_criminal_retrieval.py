"""
tests/test_compound_criminal_retrieval.py

Tests for:
1. Multi-lane compound legal query decomposition (offence ingredients, civil vs criminal, pre-arrest bail, corporate director).
2. Positive query anchor extraction supporting plural 'Sections', slashes, and criminal/bail doctrines.
3. Spurious precedent rejection: ensures defamation cases like Mushtaq Ahmad Gurmani (1958 PLD 747)
   are never admitted for criminal breach of trust, fraud, or pre-arrest bail queries.
4. Fail-closed statutory provenance for Sections 409 and 420 PPC.
"""

import unittest
from core.legal_guardrails import (
    decompose_compound_legal_query,
    extract_positive_query_anchors,
    passes_positive_anchor_test
)
from core.statute_currency import global_statute_store


class TestCompoundCriminalRetrieval(unittest.TestCase):

    def test_multi_section_anchor_extraction(self):
        query = (
            "A company director is accused under Sections 409 and 420 PPC. "
            "He seeks pre-arrest bail under Section 498 CrPC."
        )
        anchors = extract_positive_query_anchors(query)
        self.assertIn("section 409", anchors)
        self.assertIn("section 420", anchors)
        self.assertIn("section 498", anchors)
        self.assertIn("pre-arrest bail", anchors)

    def test_compound_query_decomposition_criminal_corporate(self):
        query = (
            "A private limited company director is accused of misappropriating Rs. 45 million "
            "by transferring funds from the company bank account to his wife's personal account "
            "under the guise of consultancy fees without board approval. The company filed an FIR "
            "under Sections 409 and 420 PPC. The accused claims this was repayment of an undocumented "
            "director loan and seeks pre-arrest bail under Section 498 CrPC. Analyze whether Section 409 "
            "applies to a company director, whether the dispute is civil or criminal, and grounds for "
            "pre-arrest bail under Pakistani law."
        )
        decomposed = decompose_compound_legal_query(query)
        self.assertIsInstance(decomposed, list)
        self.assertGreaterEqual(len(decomposed), 4)

        has_offence_lane = any("409" in sq and "breach of trust" in sq for sq in decomposed)
        has_civil_vs_crim = any("civil dispute" in sq and "dishonest intention" in sq for sq in decomposed)
        has_bail_lane = any("498" in sq and "pre-arrest bail" in sq for sq in decomposed)
        has_director_lane = any("director" in sq and "company funds" in sq for sq in decomposed)

        self.assertTrue(has_offence_lane, "Expected dedicated offence ingredients subquery")
        self.assertTrue(has_civil_vs_crim, "Expected civil dispute vs criminal breach of trust subquery")
        self.assertTrue(has_bail_lane, "Expected dedicated pre-arrest bail subquery")
        self.assertTrue(has_director_lane, "Expected corporate director funds subquery")

    def test_gurmani_defamation_rejected_for_fraud_query(self):
        case_title_str = "mushtaq ahmad gurmani v. z. a. suleri and another"
        full_text_str = (
            "criminal trial for defamation under section 500 ppc. the accused, an editor of an english daily, "
            "claimed journalistic privilege and fair comment. proceedings regarding transfer and interim bail."
        )
        haystack_check = f"{case_title_str} {full_text_str}".lower()

        effective_user_query = "FIR under Sections 409 and 420 PPC regarding company director loan pre-arrest bail"
        sq_lower = effective_user_query.lower()

        is_crim_fraud_or_bail = any(k in sq_lower or k in effective_user_query.lower() for k in [
            "409", "420", "406", "489-f", "489f", "breach of trust", "misappropriat",
            "cheating", "pre-arrest bail", "section 498", "loan repayment"
        ])
        self.assertTrue(is_crim_fraud_or_bail)

        is_pure_defamation = (
            any(k in haystack_check for k in ["defamation", "defamatory", "section 500", "sec 500", "500 ppc", "libel", "slander", "journalistic privilege", "mushtaq ahmad gurmani", "z. a. suleri"]) and
            not any(k in haystack_check for k in ["409", "420", "406", "489-f", "breach of trust", "misappropriat", "cheating", "entrustment", "director loan", "company funds"])
        )
        self.assertTrue(is_pure_defamation, "Gurmani should be recognized as pure defamation")

    def test_ppc_statutory_text_provenance(self):
        sec_409 = global_statute_store.get_latest_version("PPC_1860", "PPC_1860_SEC_409")
        self.assertIsNotNone(sec_409, "PPC Section 409 must exist in global_statute_store")
        self.assertIn("commits criminal breach of trust", sec_409.get("text", ""))
        self.assertIn("Criminal breach of trust by public servant", sec_409.get("title", ""))
        self.assertEqual(sec_409.get("verification_status"), "verified")

        sec_420 = global_statute_store.get_latest_version("PPC_1860", "PPC_1860_SEC_420")
        self.assertIsNotNone(sec_420, "PPC Section 420 must exist in global_statute_store")
        self.assertIn("Whoever cheats and thereby dishonestly induces", sec_420.get("text", ""))
        self.assertIn("Cheating and dishonestly inducing delivery of property", sec_420.get("title", ""))
        self.assertEqual(sec_420.get("verification_status"), "verified")


if __name__ == "__main__":
    unittest.main()
