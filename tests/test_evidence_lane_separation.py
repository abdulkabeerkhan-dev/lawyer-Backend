# tests/test_evidence_lane_separation.py
"""
Tests for Mission 1.2: Evidence-Lane Separation & Page-Slip Classification
Validates:
1. Page-slip with verified identity -> restricted (NOT quarantined)
2. Displaced text with alien identity -> quarantined
3. Physical prompt separation: authoritative_evidence vs discovery_leads
4. Mandatory limitation notice when only discovery leads are present
5. Reviewer gate rejection of unverified headnote holdings
6. Aggregate citations payload evidence_lane tagging
"""

import unittest
import asyncio
from core.legal_guardrails import get_authority_policy
from scripts.classify_corpus_trust import classify_record_trust
from core.final_review_gate import run_final_review_gate


class TestEvidenceLaneSeparation(unittest.TestCase):

    def test_page_slip_classified_as_restricted(self):
        """Case with matching parties but differing page number must be restricted, NOT quarantined."""
        record = {
            "case_id": "1969_PLD_274",
            "citation": "PLD 1969 Lahore 274",
            "title": "Bashir Ahmad v. Muhammad Rafiq",
            "full_text": (
                "PLD 1969 Lahore 374\n"
                "Before Muhammad Afzal Zullah, J.\n"
                "BASHIR AHMAD---Petitioner versus MUHAMMAD RAFIQ---Respondent\n"
                "Civil Revision No. 120 of 1968, decided on 15th January, 1969.\n\n"
                "ORDER\n\n"
                "MUHAMMAD AFZAL ZULLAH, J.---This revision petition is directed against the order..."
            )
        }
        res = classify_record_trust(record)
        self.assertEqual(res["identity_status"], "verified")
        self.assertEqual(res["citation_status"], "mismatch")
        self.assertEqual(res["retrieval_status"], "restricted", "Page slip must be restricted, NOT quarantined")
        self.assertIn("Page/citation mismatch on verified identity", res["verification_reason"])

    def test_displaced_text_classified_as_quarantined(self):
        """Displaced text where parties contradict the title must be quarantined."""
        record = {
            "case_id": "1980_SCMR_500",
            "citation": "1980 SCMR 500",
            "title": "Khan Muhammad v. State",
            "full_text": (
                "1995 CLC 1200\n"  # Displaced alien citation
                "Present: Anwarul Haq, C.J.\n"
                "FEDERATION OF PAKISTAN---Appellant versus UNITED BANK LTD---Respondent\n"
                "Civil Appeal No. 99 of 1979.\n\n"
                "JUDGMENT\n\n"
                "ANWARUL HAQ, C.J.---This appeal raises questions of banking law..."
            )
        }
        res = classify_record_trust(record)
        self.assertEqual(res["identity_status"], "conflict")
        self.assertEqual(res["citation_status"], "mismatch")
        self.assertEqual(res["retrieval_status"], "quarantined", "Displaced text must be quarantined")

    def test_authority_policy_mapping(self):
        """Verify get_authority_policy maps content types to correct authority classes."""
        self.assertEqual(get_authority_policy("full_text"), "FULL_AUTHORITY")
        self.assertEqual(get_authority_policy("mixed"), "FULL_AUTHORITY")
        self.assertEqual(get_authority_policy("order_text"), "FULL_AUTHORITY")
        self.assertEqual(get_authority_policy("headnote_only"), "HEADNOTE_DISCOVERY")
        self.assertEqual(get_authority_policy("caption_only"), "NON_AUTHORITY")
        self.assertEqual(get_authority_policy("title_only"), "NON_AUTHORITY")

    def test_reviewer_gate_headnote_policy(self):
        """The reviewer gate prompt strictly forbids attributing judicial holdings to headnotes."""
        from core.final_review_gate import REVIEWER_SYSTEM_PROMPT
        self.assertIn("NOTE ON HEADNOTE-ONLY SOURCES (DISCOVERY LEADS)", REVIEWER_SYSTEM_PROMPT)
        self.assertIn("A reported headnote indicates that this authority may address the proposition", REVIEWER_SYSTEM_PROMPT)
        self.assertIn("underlying judgment text has not been verified", REVIEWER_SYSTEM_PROMPT)

    def test_reviewer_gate_rejects_unverified_headnote_holding(self):
        """Mock reviewer simulates rejection when headnote is cited as binding judicial ratio."""
        memo = "The Supreme Court held in 2005 SCMR 100 that financial institutions must grant 90 days notice."
        context_chunks = [{
            "case_title": "Bank v. Customer",
            "neutral_citation": "2005 SCMR 100",
            "text": "2005 SCMR 100 -- Banking Companies Ordinance -- S. 2 -- Headnote summary only."
        }]

        async def mock_reviewer_failure(prompt):
            return {
                "passed": False,
                "propositions": [{
                    "claim": "Financial institutions must grant 90 days notice",
                    "cited_authority": "2005 SCMR 100",
                    "classification": "unsupported",
                    "reason": "Source is editorial headnote only; no verified judicial ratio established."
                }],
                "issues": ["2005 SCMR 100 cited as verified holding from editorial headnote."]
            }

        res = asyncio.run(run_final_review_gate(memo, context_chunks, reviewer_fn=mock_reviewer_failure))
        self.assertFalse(res["passed"])
        self.assertEqual(len(res["issues"]), 1)
        self.assertEqual(res["propositions"][0]["classification"], "unsupported")

    def test_evidence_lane_dual_section_formatting(self):
        """Simulate primary matches with both authoritative and discovery leads."""
        authoritative_context_parts = [
            "=== RETRIEVED PRECEDENT #1 [AUTHORITATIVE EVIDENCE] ===\nCASE_ID: 1958_PLD_SC_533\nCONTENT TYPE: full_text\nKEY HOLDING & JUDICIAL TEXT CONTENT:\nFull judgment text..."
        ]
        discovery_leads_parts = [
            "=== DISCOVERY LEAD #1 [PRELIMINARY LEAD ONLY] ===\nNOTICE: A reported headnote indicates that this authority may address the proposition, but the underlying judgment text has not been verified and I would not rely on it as verified authority yet.\nCASE_ID: 2005_SCMR_100\nCONTENT TYPE: headnote_only..."
        ]

        sections = []
        if authoritative_context_parts:
            sections.append(
                "=== SECTION 1: VERIFIED AUTHORITATIVE EVIDENCE (PRIMARY JUDICIAL TEXT) ===\n"
                f"Retrieved {len(authoritative_context_parts)} verified superior court precedent(s) with authentic judicial bodies.\n"
                + "\n\n".join(authoritative_context_parts)
            )
        if discovery_leads_parts:
            sections.append(
                "=== SECTION 2: PRELIMINARY LEADS / UNVERIFIED AUTHORITIES (DISCOVERY LEADS ONLY) ===\n"
                f"Retrieved {len(discovery_leads_parts)} discovery lead(s) containing secondary editorial headnotes or docket captions.\n"
                + "\n\n".join(discovery_leads_parts)
            )
        evidence_body = "\n\n".join(sections)

        self.assertIn("=== SECTION 1: VERIFIED AUTHORITATIVE EVIDENCE", evidence_body)
        self.assertIn("=== SECTION 2: PRELIMINARY LEADS / UNVERIFIED AUTHORITIES", evidence_body)
        self.assertIn("1958_PLD_SC_533", evidence_body)
        self.assertIn("2005_SCMR_100", evidence_body)

    def test_evidence_lane_only_discovery_leads_limitation_notice(self):
        """When only discovery leads are retrieved, mandatory limitation notice must trigger and Section 1 is absent."""
        authoritative_context_parts = []
        discovery_leads_parts = [
            "=== DISCOVERY LEAD #1 [PRELIMINARY LEAD ONLY] ===\nNOTICE: A reported headnote indicates that this authority may address the proposition, but the underlying judgment text has not been verified and I would not rely on it as verified authority yet.\nCASE_ID: 2005_SCMR_100\nCONTENT TYPE: headnote_only..."
        ]

        if len(authoritative_context_parts) == 0 and discovery_leads_parts:
            evidence_body = (
                "=== MANDATORY VERIFICATION LIMITATION NOTICE ===\n"
                "No verified primary judicial authority (full judgment, mixed order, or verified short order) was found in the database on point for this issue.\n"
                "Only editorial headnotes / preliminary discovery leads were retrieved.\n"
                "MANDATORY INSTRUCTIONS:\n"
                "1. You MUST explicitly state in your visible response that NO verified primary authority was found in the database.\n"
                "2. Do NOT answer the legal proposition from headnotes alone as if they were established law.\n"
                "3. You may list the discovery leads ONLY under a separate heading titled 'Preliminary Leads / Unverified Authorities' with this exact disclaimer:\n"
                "   'A reported headnote indicates that this authority may address the proposition, but the underlying judgment text has not been verified and I would not rely on it as verified authority yet.'\n\n"
                "=== SECTION 2: PRELIMINARY LEADS / UNVERIFIED AUTHORITIES (DISCOVERY LEADS ONLY) ===\n\n"
                + "\n\n".join(discovery_leads_parts)
            )

        self.assertIn("=== MANDATORY VERIFICATION LIMITATION NOTICE ===", evidence_body)
        self.assertIn("No verified primary judicial authority", evidence_body)
        self.assertIn("A reported headnote indicates that this authority may address the proposition", evidence_body)
        self.assertNotIn("=== SECTION 1: VERIFIED AUTHORITATIVE EVIDENCE", evidence_body)

    def test_weak_body_too_short_mixed_classified_as_restricted(self):
        """Mixed record with judicial body < 100 words must be classified as restricted."""
        record = {
            "case_id": "1996_SCMR_1118",
            "citation": "1996 SCMR 1118",
            "title": "Federation of Pakistan v. Muhammad Aslam",
            "full_text": (
                "1996 SCMR 1118\n"
                "Before Shafiur Rahman and Saad Saood Jan, JJ.\n"
                "FEDERATION OF PAKISTAN---Petitioner versus MUHAMMAD ASLAM---Respondent\n"
                "Civil Appeal No. 120 of 1995, decided on 15th January, 1996.\n"
                "Civil Procedure Code (V of 1908)---O. 39, Rr. 1 & 2---Temporary injunction---Grant of---\n"
                "Principles governing the grant or refusal of temporary injunctions are well settled in Pakistan jurisprudence. "
                "Held, that prima facie case, balance of convenience, and irreparable loss must co-exist before interim relief can be granted.\n\n"
                "ORDER\n\n"
                "SHAFIUR RAHMAN, J.---Leave to appeal is granted in this petition to consider whether the "
                "High Court was justified in setting aside the concurrent findings of two courts below."
            )
        }
        res = classify_record_trust(record)
        self.assertEqual(res["content_quality"], "mixed")
        self.assertEqual(res["retrieval_status"], "restricted")
        self.assertIn("Limited evidence: mixed record with short judicial body", res["verification_reason"])

    def test_robust_mixed_classified_as_trusted(self):
        """Mixed record with robust body (dispositive opening and outcome) must be trusted."""
        record = {
            "case_id": "2020_SCMR_500",
            "citation": "2020 SCMR 500",
            "title": "Muhammad Bashir v. The State",
            "full_text": (
                "2020 SCMR 500\n"
                "Before Asif Saeed Khan Khosa, C.J. and Syed Mansoor Ali Shah, J.\n"
                "MUHAMMAD BASHIR---Petitioner versus THE STATE---Respondent\n"
                "Jail Petition No. 50 of 2019, decided on 10th February, 2020.\n"
                "Control of Narcotic Substances Act (XXV of 1997)---S. 9(c)---Bail---Grant of---\n"
                "Quantity of contraband recovered from accused exceeded 1000 grams. "
                "Held, statutory bar contained in S. 51 of Act applies with full force.\n\n"
                "ORDER\n\n"
                "ASIF SAEED KHAN KHOSA, C.J.---Through this petition under Article 185(3) of the Constitution of the Islamic "
                "Republic of Pakistan 1973, the petitioner seeks post-arrest bail in case FIR No. 120 registered at Police "
                "Station City for offences under section 9(c) of the Control of Narcotic Substances Act 1997. We have heard "
                "the learned counsel for the petitioner as well as the learned Law Officer appearing for the State and have "
                "examined the record with their assistance. The quantity of contraband recovered from the personal possession "
                "of the petitioner exceeds one kilogram of charas. The report of the Chemical Examiner is in the positive. "
                "The statutory prohibition contained in section 51 of the Act of 1997 is attracted to the case in all its "
                "vigor. No malice or ulterior motive on part of the police has been shown or established. In view of the "
                "material available on record, no case for grant of bail is made out. For the reasons recorded above, this "
                "petition is devoid of any merit and the same is hereby dismissed."
            )
        }
        res = classify_record_trust(record)
        self.assertEqual(res["content_quality"], "mixed")
        self.assertEqual(res["retrieval_status"], "trusted")
        self.assertIn("Authentic judicial record", res["verification_reason"])


if __name__ == "__main__":
    unittest.main()
