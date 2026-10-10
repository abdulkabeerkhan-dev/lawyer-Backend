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


class DoctrinalRulesComprehensiveFalsePositiveSuite(unittest.TestCase):
    """
    Phase 4: Comprehensive test suite validating at least 5 false-positive
    immunity test cases for EACH of the 13 doctrinal rules.
    """

    def setUp(self):
        self.rules_by_id = {r["id"]: r for r in PATTERN_RULES}

    # 1. LA_S28_IMMUNITY (5 tests)
    def test_fp_la_s28_immunity_1_negation(self):
        r = self.rules_by_id["LA_S28_IMMUNITY"]
        s = "Section 28 of the Limitation Act does not grant government immunity against adverse possession."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_la_s28_immunity_2_distinction(self):
        r = self.rules_by_id["LA_S28_IMMUNITY"]
        s = "Section 28 is an extinguishment provision rather than a government immunity clause."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_la_s28_immunity_3_consumer_act(self):
        r = self.rules_by_id["LA_S28_IMMUNITY"]
        s = "Section 28 of the Consumer Protection Act 2005 allows the Consumer Court to condone delay."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_la_s28_immunity_4_correct_doctrine(self):
        r = self.rules_by_id["LA_S28_IMMUNITY"]
        s = "Section 28 operates to extinguish the title of the owner upon expiry of the limitation period."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_la_s28_immunity_5_criminal_matter_skip(self):
        r = self.rules_by_id["LA_S28_IMMUNITY"]
        s = "Section 28 provides no period of limitation can run against government disability."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    # 2. TPA_S49 (5 tests)
    def test_fp_tpa_s49_1_proper_registration_cite(self):
        r = self.rules_by_id["TPA_S49"]
        s = "Section 49 of the Registration Act 1908 governs the effect of non-registration."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_tpa_s49_2_dual_act_discussion(self):
        r = self.rules_by_id["TPA_S49"]
        s = "Section 53-A of the Transfer of Property Act must be read with Section 49 of the Registration Act."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_tpa_s49_3_negation(self):
        r = self.rules_by_id["TPA_S49"]
        s = "Section 49 regarding registration is not in the Transfer of Property Act."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_tpa_s49_4_distinction(self):
        r = self.rules_by_id["TPA_S49"]
        s = "Transfer of Property Act does not contain Section 49 regarding unregistered instruments."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_tpa_s49_5_unrelated_tpa_section(self):
        r = self.rules_by_id["TPA_S49"]
        s = "Under the Transfer of Property Act Section 54, sale of immovable property requires a registered deed."
        self.assertFalse(rule_matches_sentence(r, s))

    # 3. CRPC_561A_CIVIL (5 tests)
    def test_fp_crpc_561a_1_negation(self):
        r = self.rules_by_id["CRPC_561A_CIVIL"]
        s = "Section 561-A Cr.P.C. does not apply to civil injunction disputes."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_crpc_561a_2_distinction(self):
        r = self.rules_by_id["CRPC_561A_CIVIL"]
        s = "Unlike Section 561-A Cr.P.C. which governs criminal inherent powers, civil revision lies under Section 115 C.P.C."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_crpc_561a_3_criminal_matter(self):
        r = self.rules_by_id["CRPC_561A_CIVIL"]
        s = "The high court invoked 561-A to prevent abuse of process in the criminal case."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_crpc_561a_4_ambiguous_matter(self):
        r = self.rules_by_id["CRPC_561A_CIVIL"]
        s = "Section 561-A was discussed in relation to the revision proceedings."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="ambiguous"))

    def test_fp_crpc_561a_5_no_injunction_link(self):
        r = self.rules_by_id["CRPC_561A_CIVIL"]
        s = "Section 561-A has no application to an interlocutory order under Order XXXIX."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    # 4. LA_ARTICLES_AS_JURISDICTION (5 tests)
    def test_fp_la_articles_1_proper_limitation(self):
        r = self.rules_by_id["LA_ARTICLES_AS_JURISDICTION"]
        s = "Article 144 of the Limitation Act prescribes a period of twelve years."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_articles_2_jurisdictional_separation(self):
        r = self.rules_by_id["LA_ARTICLES_AS_JURISDICTION"]
        s = "The High Court exercised jurisdiction under Section 115 CPC while applying Article 144 of the Limitation Act."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_articles_3_negation(self):
        r = self.rules_by_id["LA_ARTICLES_AS_JURISDICTION"]
        s = "Articles of the Limitation Act do not confer jurisdiction upon the appellate court."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_articles_4_distinction(self):
        r = self.rules_by_id["LA_ARTICLES_AS_JURISDICTION"]
        s = "Limitation Act articles are limitation entries rather than sources of substantive jurisdiction."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_articles_5_first_schedule(self):
        r = self.rules_by_id["LA_ARTICLES_AS_JURISDICTION"]
        s = "The suit is barred under Article 113 of the Limitation Act First Schedule."
        self.assertFalse(rule_matches_sentence(r, s))

    # 5. ART_184_3_PRIVATE (5 tests)
    def test_fp_art_184_3_1_public_interest_writ(self):
        r = self.rules_by_id["ART_184_3_PRIVATE"]
        s = "The Supreme Court entertained the petition under Article 184(3) on a question of public importance relating to fundamental rights."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_art_184_3_2_appeal_distinction(self):
        r = self.rules_by_id["ART_184_3_PRIVATE"]
        s = "Private civil disputes reach the Supreme Court by petition for leave to appeal under Article 185 rather than Article 184(3)."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_art_184_3_3_negation(self):
        r = self.rules_by_id["ART_184_3_PRIVATE"]
        s = "Article 184(3) cannot be invoked to resolve private commercial disputes."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_art_184_3_4_criminal_matter_skip(self):
        r = self.rules_by_id["ART_184_3_PRIVATE"]
        s = "Petition under 184(3) in private civil dispute."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_art_184_3_5_ambiguous_matter_skip(self):
        r = self.rules_by_id["ART_184_3_PRIVATE"]
        s = "Petition under 184(3) in private civil dispute."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="general"))

    # 6. O39_R4_EXPARTE (5 tests)
    def test_fp_o39_r4_1_proper_discharge(self):
        r = self.rules_by_id["O39_R4_EXPARTE"]
        s = "The defendant filed an application under Order XXXIX Rule 4 CPC for discharge or variation of the injunction."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r4_2_negation(self):
        r = self.rules_by_id["O39_R4_EXPARTE"]
        s = "Order XXXIX Rule 4 does not provide for automatic lapse of an ex parte injunction."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r4_3_distinction(self):
        r = self.rules_by_id["O39_R4_EXPARTE"]
        s = "Notice before grant of ex parte injunction is governed by Rule 3 rather than Rule 4."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r4_4_criminal_skip(self):
        r = self.rules_by_id["O39_R4_EXPARTE"]
        s = "Rule 4 ex parte lapse occurred."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_o39_r4_5_general_matter_skip(self):
        r = self.rules_by_id["O39_R4_EXPARTE"]
        s = "Rule 4 ex parte lapse occurred."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="general"))

    # 7. O39_R3_DISOBEDIENCE (5 tests)
    def test_fp_o39_r3_1_proper_notice(self):
        r = self.rules_by_id["O39_R3_DISOBEDIENCE"]
        s = "Under Order XXXIX Rule 3 CPC, the court directed notice of the application to the opposite party."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r3_2_negation(self):
        r = self.rules_by_id["O39_R3_DISOBEDIENCE"]
        s = "Order XXXIX Rule 3 does not deal with disobedience or contempt of injunction orders."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r3_3_distinction(self):
        r = self.rules_by_id["O39_R3_DISOBEDIENCE"]
        s = "Penalty for disobedience is provided under Rule 2(3) rather than Rule 3."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r3_4_criminal_skip(self):
        r = self.rules_by_id["O39_R3_DISOBEDIENCE"]
        s = "Rule 3 disobedience contempt proceedings."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_o39_r3_5_ambiguous_skip(self):
        r = self.rules_by_id["O39_R3_DISOBEDIENCE"]
        s = "Rule 3 disobedience contempt proceedings."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="unknown"))

    # 8. O39_R2_FINAL_EXECUTION (5 tests)
    def test_fp_o39_r2_1_proper_interim_restraint(self):
        r = self.rules_by_id["O39_R2_FINAL_EXECUTION"]
        s = "The plaintiff sought a temporary injunction under Order XXXIX Rule 2 CPC to restrain ongoing breach."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r2_2_negation(self):
        r = self.rules_by_id["O39_R2_FINAL_EXECUTION"]
        s = "Order XXXIX Rule 2 does not grant final execution or permanent possession."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r2_3_distinction(self):
        r = self.rules_by_id["O39_R2_FINAL_EXECUTION"]
        s = "Order XXXIX Rule 2 provides interlocutory protection rather than final execution of a decree."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r2_4_criminal_skip(self):
        r = self.rules_by_id["O39_R2_FINAL_EXECUTION"]
        s = "Rule 2 execution of decree and permanent possession."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_o39_r2_5_ambiguous_skip(self):
        r = self.rules_by_id["O39_R2_FINAL_EXECUTION"]
        s = "Rule 2 execution of decree and permanent possession."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="ambiguous"))

    # 9. O39_R1_FINAL_DECLARATORY (5 tests)
    def test_fp_o39_r1_1_interlocutory_grant(self):
        r = self.rules_by_id["O39_R1_FINAL_DECLARATORY"]
        s = "The trial court granted temporary injunction under Order XXXIX Rule 1 CPC pending decision of the suit."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r1_2_negation(self):
        r = self.rules_by_id["O39_R1_FINAL_DECLARATORY"]
        s = "Order XXXIX Rule 1 does not grant final declaratory decrees."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r1_3_distinction(self):
        r = self.rules_by_id["O39_R1_FINAL_DECLARATORY"]
        s = "Declaratory relief must be sought under Section 42 of the Specific Relief Act rather than Order XXXIX Rule 1."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_r1_4_criminal_skip(self):
        r = self.rules_by_id["O39_R1_FINAL_DECLARATORY"]
        s = "Rule 1 final declaratory decree granted."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_o39_r1_5_ambiguous_skip(self):
        r = self.rules_by_id["O39_R1_FINAL_DECLARATORY"]
        s = "Rule 1 final declaratory decree granted."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="unknown"))

    # 10. O39_EXCLUSIVE (5 tests)
    def test_fp_o39_exclusive_1_multi_source(self):
        r = self.rules_by_id["O39_EXCLUSIVE"]
        s = "Injunctions may be granted under Order XXXIX, Section 94(c) CPC, Section 151 CPC, and the Specific Relief Act."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_exclusive_2_negation(self):
        r = self.rules_by_id["O39_EXCLUSIVE"]
        s = "Order XXXIX is not the exclusive mechanism for injunctive relief in civil litigation."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_exclusive_3_distinction(self):
        r = self.rules_by_id["O39_EXCLUSIVE"]
        s = "Civil courts possess inherent jurisdiction under Section 151 CPC alongside Order XXXIX."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="civil"))

    def test_fp_o39_exclusive_4_criminal_skip(self):
        r = self.rules_by_id["O39_EXCLUSIVE"]
        s = "Order XXXIX is the exclusive mechanism."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="criminal"))

    def test_fp_o39_exclusive_5_ambiguous_skip(self):
        r = self.rules_by_id["O39_EXCLUSIVE"]
        s = "Order XXXIX is the exclusive mechanism."
        self.assertFalse(rule_matches_sentence(r, s, matter_type="general"))

    # 11. CONTEMPT_ORD_2003 (5 tests)
    def test_fp_contempt_1_proper_cpc_remedy(self):
        r = self.rules_by_id["CONTEMPT_ORD_2003"]
        s = "The remedy for breach of a temporary injunction is attachment under Order XXXIX Rule 2(3) CPC."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_contempt_2_constitutional_mention(self):
        r = self.rules_by_id["CONTEMPT_ORD_2003"]
        s = "The court initiated contempt proceedings under Article 204 of the Constitution."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_contempt_3_distinction(self):
        r = self.rules_by_id["CONTEMPT_ORD_2003"]
        s = "Contempt of Court Ordinance is inapplicable to breach of civil status quo orders where CPC remedies suffice."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_contempt_4_negation(self):
        r = self.rules_by_id["CONTEMPT_ORD_2003"]
        s = "Contempt of Court Ordinance does not apply to civil execution proceedings."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_contempt_5_penal_remedy(self):
        r = self.rules_by_id["CONTEMPT_ORD_2003"]
        s = "Disobedience of the interim order is punishable under Order XXXIX Rule 2(3) CPC."
        self.assertFalse(rule_matches_sentence(r, s))

    # 12. LA_S5_GOVT_PROVISO (5 tests)
    def test_fp_la_s5_1_general_condonation(self):
        r = self.rules_by_id["LA_S5_GOVT_PROVISO"]
        s = "Under Section 5 of the Limitation Act, sufficient cause must be shown to condone delay."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_s5_2_government_parity(self):
        r = self.rules_by_id["LA_S5_GOVT_PROVISO"]
        s = "Government is treated at par with ordinary litigants and has no preferential treatment under Section 5."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_s5_3_negation(self):
        r = self.rules_by_id["LA_S5_GOVT_PROVISO"]
        s = "Section 5 contains no express proviso excluding the government."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_s5_4_distinction(self):
        r = self.rules_by_id["LA_S5_GOVT_PROVISO"]
        s = "Sindh Irrigation held that Section 5 requires sufficient cause rather than granting government dispensations."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_la_s5_5_private_litigant(self):
        r = self.rules_by_id["LA_S5_GOVT_PROVISO"]
        s = "The private appellant established sufficient cause under Section 5 of the Limitation Act."
        self.assertFalse(rule_matches_sentence(r, s))

    # 13. PERIOD_30_DAYS (5 tests)
    def test_fp_period_30_1_grounded_statutory_limitation(self):
        r = self.rules_by_id["PERIOD_30_DAYS"]
        s = "The appeal was preferred within thirty days as prescribed under Section 28 of the Punjab Rented Premises Act 2009."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_period_30_2_first_schedule_article(self):
        r = self.rules_by_id["PERIOD_30_DAYS"]
        s = "Under Article 156 of the Limitation Act, the period for appeal to the High Court is thirty days."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_period_30_3_general_discussion(self):
        r = self.rules_by_id["PERIOD_30_DAYS"]
        s = "The revision petition was filed within the statutory limitation period."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_period_30_4_negation(self):
        r = self.rules_by_id["PERIOD_30_DAYS"]
        s = "The statute does not prescribe a limitation of within 30 days for this revision."
        self.assertFalse(rule_matches_sentence(r, s))

    def test_fp_period_30_5_contractual_term(self):
        r = self.rules_by_id["PERIOD_30_DAYS"]
        s = "The tenant agreed to vacate within 30 days of the contractual termination notice."
        self.assertFalse(rule_matches_sentence(r, s))


if __name__ == "__main__":
    unittest.main()
