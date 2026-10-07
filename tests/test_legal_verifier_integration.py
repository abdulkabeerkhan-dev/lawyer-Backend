"""
tests/test_legal_verifier_integration.py

Regression test suite and false-positive immunity tests for the
integrated Stage-6 in-memory legal verification pipeline.
"""

import json
import time
import unittest
from pathlib import Path

from legal_ai.verification import (
    StatuteAuthorityStore,
    audit_memo,
    classify_matter_type,
    detect_topics,
    normalize_citation,
    build_pre_synthesis_trap_instructions,
    rule_matches_sentence,
    PATTERN_RULES,
)
from legal_ai.synthesis.memorandum_generator import sanitize_precedent_card

FX = Path(__file__).parent / "fixtures"
codes = lambda r: {f.code for f in r.findings}
ids = lambda r, code: [f for f in r.findings if f.code == code]


class AdversePossessionIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.store = StatuteAuthorityStore()
        with open(FX / "retrieved_adverse.json", encoding="utf-8") as f:
            self.retr = json.load(f)
        self.memo_text = (FX / "memo_adverse.txt").read_text(encoding="utf-8")
        self.res = audit_memo(
            self.memo_text,
            self.store,
            "adverse possession against provincial government",
            self.retr
        )

    def test_core_errors_caught(self):
        c = codes(self.res)
        for want in [
            "STATUTE_MISSTATEMENT",
            "PROVISION_SUBJECT_MISMATCH",
            "PROVISION_WRONG_ACT",
            "FORUM_PROVISION_MISMATCH",
            "ARTICLE_TYPE_CONFUSION",
            "MISSING_GOVERNING_PROVISION",
            "TEMPLATE_RESIDUE",
            "STATUTE_QUOTE_UNVERIFIED",
            "NO_AUTHORITY_FOR_TOPIC",
            "OVERCONFIDENT_VS_GAPS",
        ]:
            self.assertIn(want, c, f"Expected error code {want} to be caught")

    def test_missing_art_144_and_149(self):
        msgs = " ".join(f.message for f in ids(self.res, "MISSING_GOVERNING_PROVISION"))
        self.assertIn("Art. 144", msgs)
        self.assertIn("Art. 149", msgs)

    def test_unresolved_and_no_authority(self):
        self.assertEqual(self.res.confidence, "Unresolved")
        self.assertEqual(self.res.cards, [])  # irrelevant cards dropped

    def test_s28_consumer_act_not_flagged(self):
        r = audit_memo(
            "Section 28 of the Consumer Protection Act 2005 allows the Consumer Court to condone delay.",
            self.store,
            "adverse possession"
        )
        self.assertNotIn("STATUTE_MISSTATEMENT", codes(r))


class InjunctionIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.store = StatuteAuthorityStore()
        with open(FX / "retrieved_injunction.json", encoding="utf-8") as f:
            self.retr = json.load(f)
        self.memo_text = (FX / "memo_injunction.txt").read_text(encoding="utf-8")
        self.res = audit_memo(
            self.memo_text,
            self.store,
            "Order XXXIX injunction",
            self.retr
        )

    def test_errors_caught(self):
        msgs = " | ".join(f.message for f in self.res.findings)
        c = codes(self.res)
        for want in [
            "STATUTE_MISSTATEMENT",
            "PROVISION_SUBJECT_MISMATCH",
            "FORUM_PROVISION_MISMATCH",
            "TEMPLATE_RESIDUE",
            "MISSING_GOVERNING_PROVISION",
            "UNVERIFIED_STATUTE_REFERENCE",
            "OVERCLAIM_VERIFIED_LABEL",
            "UNSOURCED_PERIOD",
        ]:
            self.assertIn(want, c, f"Expected error code {want} to be caught")
        self.assertIn("R.2(3)", msgs)
        self.assertIn("R.3", msgs)
        self.assertIn("O.XXXIX R.4", msgs)

    def test_relevance_gate_keeps_only_mianoor(self):
        passing = {r.citation for r in self.res.relevance if r.passes}
        self.assertEqual(passing, {"2008 YLR 1536"})
        self.assertEqual([c["citation"] for c in self.res.cards], ["2008 YLR 1536"])

    def test_card_status_is_computed_not_boilerplate(self):
        for c in self.res.cards:
            self.assertNotIn("Verified against", c["verification_status"])
            self.assertIsNone(c["pdf_url"])

    def test_overclaim_removed_from_body(self):
        self.assertNotIn("drawn directly from", self.res.body)

    def test_no_banner_in_output(self):
        self.assertNotIn("DRAFT", self.res.render())


class HelpersAndNormalizationTest(unittest.TestCase):
    def test_pld_normalisation(self):
        self.assertEqual(normalize_citation("2025 PLD 502", "Supreme Court of Pakistan"), ("PLD 2025 SC 502", True))
        self.assertEqual(normalize_citation("2026 SCMR 190"), ("2026 SCMR 190", True))
        self.assertFalse(normalize_citation("2025 PLD 502")[1])

    def test_citation_autofix_in_body(self):
        store = StatuteAuthorityStore()
        r = audit_memo(
            "See 2025 PLD 502 for gift.\n<<<CARDS>>> [{\"citation\":\"2025 PLD 502\",\"court\":\"Supreme Court of Pakistan\"}] <<<END_CARDS>>>",
            store,
            ""
        )
        self.assertIn("PLD 2025 SC 502", r.body)

    def test_quote_verified_when_text_loaded(self):
        s = StatuteAuthorityStore()
        p = s.provision("limitation_act:section:28")
        self.assertIsNotNone(p)
        p.update(
            text="At the determination of the period hereby limited to any person for instituting a suit for possession of any property, his right to such property shall be extinguished.",
            reviewed_by="Licensed Advocate"
        )
        r = audit_memo(
            'Section 28 provides: "At the determination of the period hereby limited to any person for instituting a suit for possession of any property, his right to such property shall be extinguished."',
            s,
            "adverse possession"
        )
        self.assertNotIn("STATUTE_QUOTE_UNVERIFIED", codes(r))


class FalsePositiveImmunityTest(unittest.TestCase):
    """
    Validates that correct doctrinal distinctions and negations are NEVER falsely flagged.
    """

    def setUp(self):
        self.store = StatuteAuthorityStore()

    def test_fp_crpc_561a_contrast_civil(self):
        sentence = (
            "Unlike Section 561-A Cr.P.C. which applies in criminal proceedings, in civil injunction "
            "disputes the remedy is an appeal under Order XLIII Rule 1(r) C.P.C."
        )
        r = [x for x in PATTERN_RULES if x["id"] == "CRPC_561A_CIVIL"][0]
        self.assertFalse(rule_matches_sentence(r, sentence, matter_type="civil"))

    def test_fp_crpc_561a_explicit_negation(self):
        sentence = (
            "Section 561-A Cr.P.C. does not apply to a civil injunction dispute and cannot be invoked "
            "against an interim order under Order XXXIX."
        )
        r = [x for x in PATTERN_RULES if x["id"] == "CRPC_561A_CIVIL"][0]
        self.assertFalse(rule_matches_sentence(r, sentence, matter_type="civil"))

    def test_fp_criminal_matter_immunity(self):
        r = [x for x in PATTERN_RULES if x["id"] == "CRPC_561A_CIVIL"][0]
        sentence = "The petitioner may invoke Section 561-A Cr.P.C. to quash the criminal revision proceedings."
        self.assertFalse(rule_matches_sentence(r, sentence, matter_type="criminal"))

    def test_fp_matter_type_classification(self):
        self.assertEqual(classify_matter_type("Can adverse possession run against state land?"), "civil")
        self.assertEqual(classify_matter_type("Application for temporary injunction under Order XXXIX"), "civil")
        self.assertEqual(classify_matter_type("Pre-arrest bail under section 498 CrPC in FIR 420/406"), "criminal")
        self.assertEqual(classify_matter_type("Writ petition under Article 199 against tax assessment order"), "tax")
        self.assertEqual(classify_matter_type("Recovery suit under Financial Institutions Ordinance 2001"), "corporate")

    def test_fp_pre_synthesis_trap_instructions(self):
        instr_civ = build_pre_synthesis_trap_instructions("civil", ["injunction", "adverse_possession"])
        self.assertIn("Registration Act 1908", instr_civ)
        self.assertIn("Section 561-A Cr.P.C.", instr_civ)
        self.assertIn("Order XXXIX", instr_civ)
        self.assertIn("Section 28 Limitation Act 1908 extinguishes right", instr_civ)

    def test_audit_latency_under_50ms(self):
        memo_3000_words = (
            "This is an exhaustive legal opinion on civil injunctions.\n"
            + "Order XXXIX Rule 1 and Rule 2 apply to temporary injunctions.\n"
            + "The applicant must demonstrate a prima facie case, balance of convenience, and irreparable injury.\n"
        ) * 100
        start = time.perf_counter()
        res = audit_memo(memo_3000_words, self.store, "Order XXXIX injunction")
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed_ms, 100.0, f"Audit took {elapsed_ms:.2f} ms (must be < 100 ms)")
        print(f"\nAudit execution time for 3,000 words: {elapsed_ms:.2f} ms")


if __name__ == "__main__":
    unittest.main()
