"""
tests/test_compound_query_relevance.py

Unit and regression test suite for compound / multi-issue query relevance:
1. Query decomposition (rent eviction + bounced cheque prosecution)
2. Query planning (multi-lane assignment, matter_type, forum, provisions)
3. Quality filtering (preservation of dual civil/criminal candidates)
4. Statute injection (grounded bare-act text for PPC s.489-F and PRPA ss.15/34)
5. 7 new doctrinal verification rules and negation guards
"""

import unittest
from core.legal_guardrails import decompose_compound_legal_query
from core.legal_query_planner import create_deterministic_fallback_plan
from core.candidate_quality_filter import filter_candidate_quality_before_ranking as core_filter
from legal_ai.ranking.relevance_filter import filter_candidate_quality_before_ranking as rank_filter
from legal_ai.statutes.statute_injector import StatuteInjector
from legal_ai.verification.doctrinal_rules import (
    PATTERN_RULES,
    rule_matches_sentence,
    detect_topics,
    TOPICS_SPEC,
)


class TestCompoundQueryRelevance(unittest.TestCase):

    def setUp(self):
        self.injector = StatuteInjector()
        self.rules_by_id = {r["id"]: r for r in PATTERN_RULES}
        self.compound_query = (
            "My client owns a commercial shop in Lahore. His tenant, a company's director, "
            "stopped paying rent 8 months ago and handed him a cheque for the arrears, which bounced. "
            "Can he evict the tenant and also prosecute him over the cheque? "
            "Which forums, which limitation periods, and can both proceed at the same time?"
        )

    def test_query_decomposition_rent_and_cheque(self):
        subqueries = decompose_compound_legal_query(self.compound_query)
        self.assertGreaterEqual(len(subqueries), 3)

        # Confirm rent prong is extracted
        has_rent = any("rent" in sq.lower() or "prpa" in sq.lower() for sq in subqueries)
        self.assertTrue(has_rent, "Decomposed subqueries must contain dedicated rent/eviction query")

        # Confirm cheque prong is extracted
        has_cheque = any("cheque" in sq.lower() or "489-f" in sq.lower() for sq in subqueries)
        self.assertTrue(has_cheque, "Decomposed subqueries must contain dedicated cheque dishonour query")

        # Confirm concurrent remedies prong is extracted
        has_concurrent = any("concurrent" in sq.lower() or "simultaneous" in sq.lower() for sq in subqueries)
        self.assertTrue(has_concurrent, "Decomposed subqueries must contain concurrent civil/criminal query")

    def test_query_planner_multi_lane_generation(self):
        plan = create_deterministic_fallback_plan(self.compound_query)
        self.assertEqual(plan.province, "Punjab")

        # Matter type should contain both rent and criminal
        self.assertIn("rent", plan.matter_type)
        self.assertIn("criminal", plan.matter_type)

        # Provisions should contain both PRPA and PPC 489-F
        prov_strs = " ".join(plan.provisions)
        self.assertIn("489", prov_strs)
        self.assertIn("PRPA", prov_strs)

        # Lanes should have distinct lane names for each issue
        lane_names = [l["lane"] for l in plan.search_lanes]
        self.assertIn("cheque_dishonour_489f", lane_names)
        self.assertIn("rent_tribunal_eviction", lane_names)

        # Forum should specify Rent Tribunal and Magistrate
        self.assertIn("Rent Tribunal", plan.forum)
        self.assertIn("Magistrate", plan.forum)

    def test_statute_injector_retrieves_verbatim_489f(self):
        plan = create_deterministic_fallback_plan(self.compound_query)
        res = self.injector.inject_statutory_framework(plan, self.compound_query)
        block = res["statute_block"]

        # Confirm verbatim text of Section 489-F PPC is injected
        self.assertIn("Section 489-F", block)
        self.assertIn("dishonestly issues a cheque", block)
        self.assertIn("re-payment of a loan or fulfilment of an obligation", block)
        self.assertNotIn("[NOT_RETRIEVED]", block.split("Section 489-F")[1].split("---")[0])

    def test_candidate_quality_filter_preserves_both_rent_and_cheque(self):
        plan = create_deterministic_fallback_plan(self.compound_query)

        raw_candidates = [
            {
                "case_id": "2020_scmr_101",
                "title": "Muhammad Akram v. Special Judge (Rent), Lahore",
                "court": "Supreme Court of Pakistan",
                "preview": "Eviction application under Section 15 of Punjab Rented Premises Act 2009 for default in rent payment. Bar on civil courts under Section 34.",
            },
            {
                "case_id": "2019_scmr_1083",
                "title": "Mian Allah Ditta v. The State",
                "court": "Supreme Court of Pakistan",
                "preview": "Section 489-F PPC. Dishonestly issuing a cheque towards repayment of loan or obligation. Bounced cheque and criminal prosecution.",
            },
            {
                "case_id": "2018_scmr_500",
                "title": "State v. Narcotics Smuggler",
                "court": "Supreme Court of Pakistan",
                "preview": "Control of Narcotic Substances Act CNSA recovery of charas heroin.",
            }
        ]

        # Test both core filter and ranking filter
        clean_core, rej_core = core_filter(raw_candidates, plan)
        clean_rank, rej_rank = rank_filter(raw_candidates, plan)

        # Rent case and Cheque case MUST both be preserved!
        core_cids = [c["case_id"] for c in clean_core]
        rank_cids = [c["case_id"] for c in clean_rank]

        self.assertIn("2020_scmr_101", core_cids, "Rent case must not be dropped by quality filter")
        self.assertIn("2019_scmr_1083", core_cids, "Cheque case must not be dropped by quality filter")
        self.assertNotIn("2018_scmr_500", core_cids, "Narcotics case should be dropped")

        self.assertIn("2020_scmr_101", rank_cids, "Rent case must not be dropped by ranking filter")
        self.assertIn("2019_scmr_1083", rank_cids, "Cheque case must not be dropped by ranking filter")
        self.assertNotIn("2018_scmr_500", rank_cids, "Narcotics case should be dropped")

    def test_doctrinal_rule_ni_act_s138(self):
        rule = self.rules_by_id["NI_ACT_S138_IMPORT"]
        # Trigger
        bad = "The landlord filed a complaint under Section 138 of the Negotiable Instruments Act for the bounced cheque."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Negation / Distinction immunity
        good1 = "Unlike Section 138 of the Negotiable Instruments Act in India, Pakistan law prosecutes cheques under Section 489-F PPC."
        self.assertFalse(rule_matches_sentence(rule, good1))

        good2 = "Section 138 Negotiable Instruments Act does not apply in Pakistan."
        self.assertFalse(rule_matches_sentence(rule, good2))

    def test_doctrinal_rule_limitation_act_criminal(self):
        rule = self.rules_by_id["LIMITATION_ACT_CRIMINAL"]
        # Trigger
        bad = "The limitation period for lodging an FIR under Section 489-F PPC is governed by the Limitation Act."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Negation / Distinction immunity
        good = "The Limitation Act does not prescribe any period of limitation for criminal prosecutions or lodging an FIR."
        self.assertFalse(rule_matches_sentence(rule, good))

    def test_doctrinal_rule_punjab_tenancy_act(self):
        rule = self.rules_by_id["PUNJAB_TENANCY_ACT_FOR_RENT"]
        # Trigger
        bad = "Eviction from the commercial shop in Lahore is sought under the Punjab Tenancy Act."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Distinction immunity
        good = "The Punjab Tenancy Act applies only to agricultural tenancies, unlike urban rented premises which are governed by PRPA 2009."
        self.assertFalse(rule_matches_sentence(rule, good))

    def test_doctrinal_rule_o42_r1(self):
        rule = self.rules_by_id["O42_R1_JURISDICTION"]
        # Trigger
        bad = "The landlord instituted a suit for eviction in the original jurisdiction under Order XLII Rule 1 CPC."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Distinction
        good = "Order XLII Rule 1 CPC prescribes procedure for second appeals in the High Court under Section 100 CPC."
        self.assertFalse(rule_matches_sentence(rule, good))

    def test_doctrinal_rule_s34_cpc(self):
        rule = self.rules_by_id["S34_CPC_MULTIPLE_REMEDIES"]
        # Trigger
        bad = "Section 34 CPC authorizes the plaintiff to pursue multiple remedies concurrently."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Distinction
        good = "Section 34 CPC empowers the court to award interest and cost of funds in a decree for payment of money."
        self.assertFalse(rule_matches_sentence(rule, good))

    def test_doctrinal_rule_s200_cognizance(self):
        rule = self.rules_by_id["S200_COGNIZANCE"]
        # Trigger
        bad = "The Magistrate takes cognizance under Section 200 Cr.P.C. upon receiving the direct complaint."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Distinction
        good = "Cognizance is taken under Section 190 Cr.P.C., whereupon examination of the complainant proceeds under Section 200 Cr.P.C."
        self.assertFalse(rule_matches_sentence(rule, good))

    def test_doctrinal_rule_s228_charge(self):
        rule = self.rules_by_id["S228_CHARGE"]
        # Trigger
        bad = "The charge is framed under Section 228 Cr.P.C. against the accused."
        self.assertTrue(rule_matches_sentence(rule, bad))

        # Distinction
        good = "In Pakistani Cr.P.C., Section 228 governs alteration of charge, while formal charge is framed under Section 242 Cr.P.C."
        self.assertFalse(rule_matches_sentence(rule, good))


if __name__ == "__main__":
    unittest.main()
