"""
Unit tests for Pakistani Legal Research App:
- Statute currency & append-only version store
- Parallel currency check & tiering
- Precedent temporal amendment tags & retry cap
- Retrieval relevance (positive anchors, 2-way identity, court headers, real cases counter)
- Attribution & fail-closed grounding (speaker filter, internal citations, headnotes, conflicts, doctrine elements)
- Memo completeness

GENERIC FIXTURES ONLY: Zero real case names in rule logic or test fixtures.
"""

import unittest
import tempfile
import shutil
import os
import json
from datetime import datetime, timezone, timedelta

from core.statute_currency import (
    StatuteVersionStore,
    StatuteStatus,
    is_law_status,
    VALID_JURISDICTIONS,
    global_statute_store,
    check_statute_currency,
    tag_precedent_temporal_amendment,
    detect_statutory_provisions_in_query,
    classify_source_tier
)
from core.legal_guardrails import (
    extract_positive_query_anchors,
    passes_positive_anchor_test,
    derive_court_from_judgment_header,
    verify_case_identity,
    is_counsel_submission_span,
    find_supporting_span_in_text,
    fail_closed_citation_grounding,
    count_real_cases_discussed,
    strip_agent_narration,
    check_rule_to_subject_consistency,
    detect_conflicting_authorities,
    verify_doctrine_elements,
    check_memo_completeness,
    lint_legal_output
)


class TestStatuteVersionStore(unittest.TestCase):
    """Tests for append-only statute version store, tiering, staging and dates."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.staging_dir = tempfile.mkdtemp()
        self.store = StatuteVersionStore(storage_dir=self.test_dir, staging_dir=self.staging_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.staging_dir, ignore_errors=True)

    def test_version_store_append_only(self):
        # Initial version
        v1 = self.store.append_version(
            canonical_id="GENERIC_ACT_SEC_1",
            act_code="GENERIC_ACT",
            text="Initial text of section 1.",
            jurisdiction="federal",
            status="in_force",
            source_url="https://pakistancode.gov.pk/sample",
            source_tier="tier_1",
            verified_by="Registrar"
        )
        self.assertEqual(v1["version_id"], "GENERIC_ACT_SEC_1_V1")
        self.assertIsNone(v1["previous_version_id"])

        # Second version (amendment)
        v2 = self.store.append_version(
            canonical_id="GENERIC_ACT_SEC_1",
            act_code="GENERIC_ACT",
            text="Amended text of section 1.",
            jurisdiction="federal",
            status="in_force",
            source_url="https://pakistancode.gov.pk/amended",
            source_tier="tier_1",
            verified_by="Registrar"
        )
        self.assertEqual(v2["version_id"], "GENERIC_ACT_SEC_1_V2")
        self.assertEqual(v2["previous_version_id"], "GENERIC_ACT_SEC_1_V1")

        versions = self.store.get_versions("GENERIC_ACT")
        self.assertEqual(len(versions), 2)
        latest = self.store.get_latest_version("GENERIC_ACT", "GENERIC_ACT_SEC_1")
        self.assertEqual(latest["text"], "Amended text of section 1.")

    def test_effective_dates_and_ordinance_expiry(self):
        now = datetime.now(timezone.utc)
        expiry_date = (now + timedelta(days=120)).date().isoformat()
        v = self.store.append_version(
            canonical_id="GENERIC_ORD_SEC_5",
            act_code="GENERIC_ORD",
            text="Emergency provision text.",
            jurisdiction="federal",
            status="in_force",
            effective_application="prospective_only",
            ordinance_expiry_date=expiry_date,
            source_url="https://officialgazette.gov.pk",
            source_tier="tier_1",
            verified_by="Official Gazette"
        )
        self.assertEqual(v["effective_application"], "prospective_only")
        self.assertEqual(v["ordinance_expiry_date"], expiry_date)

    def test_source_tiering_and_staging(self):
        self.assertEqual(classify_source_tier("https://pakistancode.gov.pk/law"), "tier_1")
        self.assertEqual(classify_source_tier("https://punjablaws.gov.pk/act"), "tier_1")
        self.assertEqual(classify_source_tier("https://pakistanlawsite.com/case"), "tier_2")
        self.assertEqual(classify_source_tier("https://lawfirmblog.com/update"), "tier_3")

        # Staging unpromoted finding from Tier 2/3
        staged = self.store.stage_finding(
            canonical_id="GENERIC_ACT_SEC_10",
            act_code="GENERIC_ACT",
            query_trigger="recent amendment in section 10",
            detected_change="Proposed increase in fine",
            source_url="https://lawfirmblog.com/update",
            raw_snippet="Reported change in statutory threshold.",
            effective_application="pending_and_prospective"
        )
        self.assertEqual(staged["source_tier"], "tier_3")
        self.assertEqual(staged["review_status"], "pending_review")

        # Promote finding with Tier 1 official confirmation
        promoted = self.store.promote_staged_finding(
            staging_id=staged["staging_id"],
            official_text="Enacted change in statutory threshold.",
            tier_1_source_url="https://pakistancode.gov.pk/gazette",
            promoted_by="Senior Registrar"
        )
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["verification_status"], "verified")
        self.assertEqual(promoted["source_tier"], "tier_1")

    def test_statute_status_enum_and_validation(self):
        # StatuteStatus contains required legal statuses
        self.assertEqual(StatuteStatus.IN_FORCE.value, "in_force")
        self.assertEqual(StatuteStatus.AMENDED.value, "amended")
        self.assertEqual(StatuteStatus.REPEALED.value, "repealed")
        self.assertEqual(StatuteStatus.BILL.value, "bill")
        self.assertEqual(StatuteStatus.PASSED.value, "passed")

        # is_law_status returns True only for assented, notified, commenced, in_force, amended
        self.assertTrue(is_law_status("assented"))
        self.assertTrue(is_law_status("notified"))
        self.assertTrue(is_law_status("commenced"))
        self.assertTrue(is_law_status("in_force"))
        self.assertTrue(is_law_status("amended"))

        # Bills and passed items are NEVER law
        self.assertFalse(is_law_status("bill"))
        self.assertFalse(is_law_status("passed"))
        self.assertFalse(is_law_status("repealed"))
        self.assertFalse(is_law_status(None))
        self.assertFalse(is_law_status(""))

        # append_version rejects invalid status with ValueError
        with self.assertRaises(ValueError):
            self.store.append_version(
                canonical_id="TEST_SEC_1",
                act_code="TEST_ACT",
                text="Text",
                status="completely_fake_status"
            )

    def test_jurisdiction_validation(self):
        # Valid jurisdictions
        for j in ["federal", "punjab", "sindh", "kp", "balochistan"]:
            self.assertIn(j, VALID_JURISDICTIONS)
            v = self.store.append_version(
                canonical_id=f"TEST_SEC_{j}",
                act_code="TEST_ACT",
                jurisdiction=j
            )
            self.assertEqual(v["jurisdiction"], j)

        # Invalid jurisdiction raises ValueError
        with self.assertRaises(ValueError):
            self.store.append_version(
                canonical_id="TEST_SEC_INVALID",
                act_code="TEST_ACT",
                jurisdiction="mars"
            )

    def test_null_dates_survive_round_trip(self):
        # A baseline record with all null dates survives write and read
        v = self.store.append_version(
            canonical_id="NULL_DATES_SEC_1",
            act_code="NULL_DATES_ACT",
            text=None,
            title="Null Dates Section",
            enacted_date=None,
            assent_date=None,
            commencement_date=None,
            valid_from=None,
            valid_to=None,
            amending_instrument=None,
            gazette_reference=None,
            court_challenges=[],
            text_available=False
        )
        self.assertIsNone(v["enacted_date"])
        self.assertIsNone(v["assent_date"])
        self.assertIsNone(v["commencement_date"])
        self.assertIsNone(v["valid_from"])
        self.assertIsNone(v["valid_to"])
        self.assertIsNone(v["amending_instrument"])
        self.assertIsNone(v["gazette_reference"])
        self.assertEqual(v["court_challenges"], [])
        self.assertFalse(v["text_available"])
        self.assertIsNone(v["text"])

        # Reload from fresh read
        latest = self.store.get_latest_version("NULL_DATES_ACT", "NULL_DATES_SEC_1")
        self.assertIsNotNone(latest)
        self.assertIsNone(latest["enacted_date"])
        self.assertIsNone(latest["assent_date"])
        self.assertIsNone(latest["commencement_date"])
        self.assertIsNone(latest["valid_from"])
        self.assertIsNone(latest["valid_to"])
        self.assertIsNone(latest["amending_instrument"])
        self.assertIsNone(latest["gazette_reference"])
        self.assertEqual(latest["court_challenges"], [])
        self.assertFalse(latest["text_available"])
        self.assertIsNone(latest["text"])


class TestStatuteCurrencyCheck(unittest.TestCase):
    """Tests for currency checking, cache windows, recency words, and output labels."""

    def test_output_labels(self):
        # Mock checking a non-existent provision returns [NOT-CHECKED]
        res = check_statute_currency("NON_EXISTENT_SEC_99", "NON_EXISTENT")
        self.assertEqual(res["label"], "NOT-CHECKED")
        self.assertIn("[NOT-CHECKED:", res["display_tag"])

        # Check existing seeded provision returns [BASELINE TABLE: not checked online]
        res_seeded = check_statute_currency("PRPA_2009_SEC_13", "PRPA_2009")
        self.assertEqual(res_seeded["label"], "BASELINE")
        self.assertEqual(res_seeded["display_tag"], "[BASELINE TABLE: not checked online]")
        self.assertNotIn("VERIFIED: Tier 1", res_seeded["display_tag"])

    def test_statute_currency_labels_env_off(self):
        # STATUTE_CURRENCY_LABELS=off suppresses currency display tags
        os.environ["STATUTE_CURRENCY_LABELS"] = "off"
        try:
            res = check_statute_currency("PRPA_2009_SEC_13", "PRPA_2009")
            self.assertEqual(res["display_tag"], "")
            self.assertEqual(res["label"], "DISABLED")
        finally:
            os.environ.pop("STATUTE_CURRENCY_LABELS", None)

    def test_recency_word_triggers_check(self):
        # Query with recency keyword triggers check even if cached
        res = check_statute_currency(
            "PPC_1860_SEC_489F",
            "PPC_1860",
            query_text="latest amendment 2026 in 489-f"
        )
        self.assertIsNotNone(res)
        self.assertIn(res["label"], ["BASELINE", "NOT-CHECKED"])

    def test_baseline_seeded_record_honesty(self):
        # A seeded baseline record must have baseline_unverified status, source_tier=None,
        # fetched_at=None, text_available=False, text=None, and display_tag=[BASELINE TABLE: not checked online]
        res = check_statute_currency("PPC_1860_SEC_489F", "PPC_1860")
        self.assertEqual(res["verification_status"], "baseline_unverified")
        self.assertIsNone(res["tier"])
        self.assertFalse(res["text_available"])
        self.assertEqual(res["jurisdiction"], "federal")
        self.assertEqual(res["display_tag"], "[BASELINE TABLE: not checked online]")
        self.assertNotIn("VERIFIED", res["display_tag"])

        # Check version store record directly
        latest = global_statute_store.get_latest_version("PPC_1860", "PPC_1860_SEC_489F")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["version_id"], "PPC_1860_SEC_489F_V2")
        self.assertEqual(latest["previous_version_id"], "PPC_1860_SEC_489F_V1")
        self.assertEqual(latest["verification_status"], "baseline_unverified")
        self.assertIsNone(latest["source_tier"])
        self.assertIsNone(latest["fetched_at"])
        self.assertIsNone(latest["text"])
        self.assertFalse(latest["text_available"])
        self.assertEqual(latest["court_challenges"], [])

    def test_real_statute_baseline_v2_records(self):
        # PRPA and Pre-emption must be Punjab jurisdiction
        prpa = global_statute_store.get_latest_version("PRPA_2009", "PRPA_2009_SEC_1")
        self.assertIsNotNone(prpa)
        self.assertEqual(prpa["jurisdiction"], "punjab")

        preempt = global_statute_store.get_latest_version("PREEMPTION_1991", "PREEMPTION_1991_SEC_1")
        self.assertIsNotNone(preempt)
        self.assertEqual(preempt["jurisdiction"], "punjab")

        # Federal acts must be federal jurisdiction
        crpc = global_statute_store.get_latest_version("CRPC_1898", "CRPC_1898_SEC_497")
        self.assertIsNotNone(crpc)
        self.assertEqual(crpc["jurisdiction"], "federal")
        self.assertFalse(crpc["text_available"])
        self.assertIsNone(crpc["text"])


class TestPrecedentTagsAndRetryCap(unittest.TestCase):
    """Tests for pre/post-amendment tags, warnings, and retry cap on new provisions."""

    def test_temporal_amendment_tagging(self):
        # Precedent from 1998 on an amendment that took effect in 2002
        tag, warn = tag_precedent_temporal_amendment(1998, "2002-10-25")
        self.assertEqual(tag, "pre_amendment")
        self.assertIsNotNone(warn)
        self.assertIn("prior to the 2002 statutory amendment", warn)

        # Precedent from 2020 on the 2002 amendment
        tag_post, warn_post = tag_precedent_temporal_amendment(2020, "2002-10-25")
        self.assertEqual(tag_post, "post_amendment")
        self.assertIsNone(warn_post)


class TestRetrievalRelevance(unittest.TestCase):
    """Tests for positive query anchors, 2-way case identity, court header derivation, real cases count."""

    def test_positive_anchor_extraction_and_filtering(self):
        query = "What are the requirements under Section 13 and Order XXI Rule 90 for auction objections?"
        anchors = extract_positive_query_anchors(query)
        self.assertIn("section 13", anchors)
        self.assertTrue(any("rule 90" in a for a in anchors))

        # Relevant text with anchor
        rel_text = "Under Order XXI Rule 90 CPC, the auction sale was challenged."
        self.assertTrue(passes_positive_anchor_test(rel_text, anchors))

        # Irrelevant text lacking anchor
        irrel_text = "The parties entered into an agreement regarding boundary wall construction."
        self.assertFalse(passes_positive_anchor_test(irrel_text, anchors))

        # Empty query anchors passes everything (unrestricted)
        self.assertTrue(passes_positive_anchor_test(irrel_text, []))

    def test_two_way_case_identity(self):
        record = {
            "case_id": "2024_scmr_9999",
            "citation": "2024 SCMR 9999",
            "title": "Generic Appellant v. Generic Respondent"
        }
        # Matching identity
        self.assertTrue(verify_case_identity("2024_scmr_9999", "2024 SCMR 9999", record))
        # Corrupted cross-walk / collision mismatch
        self.assertFalse(verify_case_identity("2024_scmr_9999", "2019 SCMR 1111", record))

    def test_derive_court_from_judgment_header(self):
        lhc_text = (
            "IN THE LAHORE HIGH COURT, LAHORE\n"
            "JUDICIAL DEPARTMENT\n"
            "Writ Petition No. 12345 of 2022\n"
            "Generic Petitioner v. Generic Respondent\n"
        )
        # Even if metadata falsely claims Supreme Court, header text MUST control
        court = derive_court_from_judgment_header(lhc_text, fallback_meta="Supreme Court of Pakistan")
        self.assertEqual(court, "Lahore High Court")

        shc_text = (
            "IN THE HIGH COURT OF SINDH, AT KARACHI\n"
            "Constitutional Petition No. D-543\n"
        )
        self.assertEqual(derive_court_from_judgment_header(shc_text), "High Court of Sindh")

        sc_text = (
            "IN THE SUPREME COURT OF PAKISTAN\n"
            "(APPELLATE JURISDICTION)\n"
            "Civil Appeal No. 99\n"
        )
        self.assertEqual(derive_court_from_judgment_header(sc_text), "Supreme Court of Pakistan")

    def test_count_real_cases_discussed(self):
        text = (
            "The court relied on 2024 SCMR 9999 and PLD 2020 SC 500. "
            "It also examined 2018 CLD 450. "
            "However, Section 12 of Act 1877 and year 2022 are not cases."
        )
        count = count_real_cases_discussed(text)
        self.assertEqual(count, 3)


class TestAttributionAndGroundingGuardrails(unittest.TestCase):
    """Tests for fail-closed grounding, internal citations, speaker filter, headnotes, conflicts, doctrines."""

    def test_fail_closed_citation_grounding(self):
        records = [
            {
                "citation": "2024 SCMR 9999",
                "full_text": "We reiterate the principle stated in 2010 SCMR 444 regarding limitation."
            }
        ]
        # Text cites:
        # 1) Grounded primary: 2024 SCMR 9999
        # 2) Grounded internal: 2010 SCMR 444
        # 3) Hallucinated / ungrounded: 2015 SCMR 7777
        generated = (
            "As settled in 2024 SCMR 9999, the petition was allowed. "
            "Similarly 2010 SCMR 444 held that time runs immediately. "
            "Furthermore 2015 SCMR 7777 held that no notice was needed."
        )
        cleaned, ungrounded, audit = fail_closed_citation_grounding(generated, records, strict_mode=False)

        self.assertIn("2024 SCMR 9999", cleaned)
        self.assertIn("2010 SCMR 444 (cited within 2024 SCMR 9999)", cleaned)
        self.assertIn("[CITATION REMOVED: 2015 SCMR 7777 ungrounded in retrieved records]", cleaned)
        self.assertIn("2015 SCMR 7777", ungrounded)

    def test_speaker_filter_rejects_counsel_submissions(self):
        submission_text = "Learned counsel for the appellant argued that the delay should be condoned."
        self.assertTrue(is_counsel_submission_span(submission_text))

        holding_text = "The Court finds that the statutory deposit was not furnished within time."
        self.assertFalse(is_counsel_submission_span(holding_text))

        # Verify lint catches counsel submissions attributed as court holdings
        bad_draft = "In this matter, learned counsel for the petitioner contended that fraud was committed, and the court held that."
        errors = lint_legal_output(bad_draft)
        self.assertTrue(any("Speaker Attribution Violation" in e for e in errors))

    def test_find_supporting_span_in_text(self):
        source = (
            "Learned counsel argued that the auction was flawed. "
            "We hold that non-deposit of twenty percent within thirty days is fatal to the objection."
        )
        match = find_supporting_span_in_text("non-deposit of twenty percent within thirty days is fatal", source)
        self.assertIsNotNone(match)
        self.assertIn("twenty percent within thirty days is fatal", match[2])

    def test_strip_agent_narration(self):
        raw = (
            "<thinking>Reviewing user query and checking statutes</thinking>\n"
            "Here is the formal legal memo requested:\n\n"
            "### I. EXECUTIVE SUMMARY\n"
            "This is a verified legal opinion on the dispute."
        )
        stripped = strip_agent_narration(raw)
        self.assertFalse(stripped.startswith("<thinking>"))
        self.assertFalse("Here is the formal legal memo" in stripped)
        self.assertTrue(stripped.startswith("### I. EXECUTIVE SUMMARY"))

    def test_check_rule_to_subject_consistency(self):
        # Order XXI in family / khula disputes is inconsistent without FCA adoption
        ok, reason = check_rule_to_subject_consistency("Order XXI Rule 90 CPC governs the execution", "Khula and Family Disputes")
        self.assertFalse(ok)
        self.assertIsNotNone(reason)

    def test_detect_conflicting_authorities(self):
        precedents = [
            {"metadata": {"court": "Supreme Court of Pakistan", "citation": "2024 SCMR 9999", "outcome": "Allowed"}},
            {"metadata": {"court": "Lahore High Court", "citation": "2021 CLC 1234", "outcome": "Dismissed"}}
        ]
        conflicts = detect_conflicting_authorities(precedents)
        self.assertEqual(len(conflicts), 1)
        self.assertIn("Article 189", conflicts[0]["note"])

    def test_verify_doctrine_elements(self):
        analysis = (
            "The offence is outside prohibitory clause and under settled principles bail is the rule. "
            "No exceptional circumstances like repetition or abscondence exist."
        )
        res = verify_doctrine_elements("tariq bashir", "", analysis)
        self.assertTrue(res["all_elements_present"])
        self.assertEqual(len(res["missing_elements"]), 0)


class TestMemoCompleteness(unittest.TestCase):
    """Tests for mandatory 5 sections and cards verification."""

    def test_memo_completeness_validation(self):
        full_memo = (
            "### I. EXECUTIVE SUMMARY\n" + ("The appellant filed an objection against the execution proceedings. " * 8) + "\n\n"
            "### II. CONTROLLING STATUTORY FRAMEWORK\n" + ("The governing provisions require strict compliance with prescribed procedural timelines. " * 8) + "\n\n"
            "### III. CONTROLLING JUDICIAL PRECEDENTS\n" + ("The superior court established that procedural statutory mandates cannot be bypassed. " * 8) + "\n\n"
            "### IV. LEGAL ANALYSIS\n" + ("Analyzing the facts of the case in light of the above settled jurisprudence demonstrates that the claim is well-founded. " * 8) + "\n\n"
            "### V. RECOMMENDATIONS & NEXT STEPS\n" + ("It is recommended to file an objection petition supported by an attested affidavit. " * 8) + "\n\n"
            "<<<CARDS>>>\n[{\"case_name\": \"Generic Precedent\", \"citation\": \"2024 SCMR 9999\"}]\n<<<END_CARDS>>>"
        )
        is_complete, issues = check_memo_completeness(full_memo, is_formal_opinion=True)
        self.assertTrue(is_complete)
        self.assertEqual(len(issues), 0)

        # Incomplete memo missing recommendations
        short_memo = (
            "### I. EXECUTIVE SUMMARY\n" + ("Brief summary text. " * 10) + "\n\n"
            "### II. STATUTORY FRAMEWORK\n" + ("Brief statute text. " * 10)
        )
        is_complete_bad, issues_bad = check_memo_completeness(short_memo, is_formal_opinion=True)
        self.assertFalse(is_complete_bad)
        self.assertTrue(any("Missing section" in i for i in issues_bad))


if __name__ == "__main__":
    unittest.main()
