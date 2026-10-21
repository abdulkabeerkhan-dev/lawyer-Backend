import unittest
from core.statute_currency import detect_statutory_provisions_in_query
from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.statutes.statute_injector import StatuteInjector
from legal_ai.verification.claim_verifier import verify_and_scrub_memo_claims
from legal_ai.verification.doctrinal_rules import build_pre_synthesis_trap_instructions


class TestBailStatutoryGrounding(unittest.TestCase):

    def setUp(self):
        self.bail_query = (
            "A person is arrested without a warrant in Pakistan. Under which section of which law "
            "can they seek bail? Does it matter whether the offence is bailable or non-bailable, "
            "and which court has jurisdiction in each scenario?"
        )

    def test_intent_detection_identifies_exact_crpc_provisions(self):
        provisions = detect_statutory_provisions_in_query(self.bail_query)
        prov_cids = [p[0] for p in provisions]
        self.assertIn("CRPC_1898_SEC_496", prov_cids)
        self.assertIn("CRPC_1898_SEC_497", prov_cids)
        self.assertIn("CRPC_1898_SEC_498", prov_cids)
        self.assertIn("CRPC_1898_SEC_54", prov_cids)
        self.assertIn("CRPC_1898_SEC_61", prov_cids)

    def test_query_planner_classifies_as_post_arrest_bail(self):
        plan = create_deterministic_fallback_plan(self.bail_query)
        self.assertIn("post-arrest bail", plan.legal_domain)
        self.assertIn("Section 496 CrPC", plan.provisions)
        self.assertIn("Section 497 CrPC", plan.provisions)
        self.assertIn("Section 498 CrPC", plan.provisions)
        # Dedicated search lanes
        lane_names = [l["lane"] for l in plan.search_lanes]
        self.assertIn("bail_bailable_s496", lane_names)
        self.assertIn("bail_non_bailable_s497", lane_names)

    def test_statute_injector_injects_full_crpc_framework(self):
        injector = StatuteInjector()
        res = injector.inject_statutory_framework(None, query_text=self.bail_query)
        injected = res.get("injected_provisions", [])
        self.assertTrue(any("Section 496" in p for p in injected))
        self.assertTrue(any("Section 497" in p for p in injected))
        self.assertTrue(any("Section 498" in p for p in injected))
        # Verbatim text present on record
        with_text = res.get("provisions_with_text", [])
        self.assertTrue(any("Section 496" in p for p in with_text))
        self.assertTrue(any("Section 497" in p for p in with_text))

    def test_claim_verifier_scrubs_hallucinated_article_12_crpc(self):
        hallucinated_text = (
            "Sessions Court (Article 12 Cr.P.C.): Has full jurisdiction over bail applications. "
            "Bailable offences (Section 497(1)): Grant of bail is a right. "
            "If bail is refused, an appeal lies to the High Court under Section 561-A Cr.P.C. or Article 199."
        )
        res = verify_and_scrub_memo_claims(hallucinated_text)
        self.assertTrue(res.has_violations)
        # Verify scrubbing
        self.assertNotIn("Article 12 Cr.P.C.", res.cleaned_text)
        self.assertIn("Sections 497/498 Cr.P.C.", res.cleaned_text)
        self.assertNotIn("Section 497(1)", res.cleaned_text)
        self.assertIn("Section 496 Cr.P.C.", res.cleaned_text)

    def test_doctrinal_rules_trap_instructions_include_bail_binary(self):
        traps = build_pre_synthesis_trap_instructions(
            matter_type=["criminal", "post-arrest bail"],
            query_text=self.bail_query
        )
        self.assertIn("Section 496 Cr.P.C.", traps)
        self.assertIn("POST-ARREST BAIL STRATEGY", traps)
        self.assertIn("Section 12 Cr.P.C. relates to Special Magistrates", traps)


if __name__ == "__main__":
    unittest.main()
