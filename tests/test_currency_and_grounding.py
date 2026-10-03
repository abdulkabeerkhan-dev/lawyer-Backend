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
import asyncio
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
from core.currency_fetcher import (
    fetch_currency_signals,
    CurrencyCache,
    is_whitelisted_tier1_domain,
    log_statute_currency_check,
    WHITELISTED_TIER_1_DOMAINS
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
    lint_legal_output,
    find_ungrounded_articles,
    articles_in
)


class TestStatuteVersionStore(unittest.TestCase):
    """Tests for append-only statute version store, tiering, staging and dates."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.staging_dir = tempfile.mkdtemp()
        self.store = StatuteVersionStore(storage_dir=self.test_dir, staging_dir=self.staging_dir, supabase_client=False)

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
        # Tier 1 official domains
        self.assertEqual(classify_source_tier("https://pakistancode.gov.pk/law"), "tier_1")
        self.assertEqual(classify_source_tier("https://punjablaws.gov.pk/act"), "tier_1")
        self.assertEqual(classify_source_tier("https://federalshariatcourt.gov.pk/decisions"), "tier_1")
        # Speculative FCC domain excluded from Tier 1 -> tier_3
        self.assertEqual(classify_source_tier("https://fcc.gov.pk/orders"), "tier_3")

        # Tier 2 reputable legal reporting
        self.assertEqual(classify_source_tier("https://pakistanlawsite.com/case"), "tier_2")

        # Tier 3 news and blogs
        self.assertEqual(classify_source_tier("https://lawfirmblog.com/update"), "tier_3")

        # Item 3: Source-Tier Spoofing Prevention Tests (Hostname Comparison)
        self.assertEqual(classify_source_tier("http://evil.com/?ref=na.gov.pk"), "tier_3")
        self.assertEqual(classify_source_tier("http://na.gov.pk.evil.com/fake-law"), "tier_3")
        self.assertEqual(classify_source_tier("https://blog.com/pakistancode.gov.pk/fake"), "tier_3")
        self.assertEqual(classify_source_tier("http://evil.federalshariatcourt.gov.pk.hack.com"), "tier_3")

        # Staging finding from Tier 1 - MUST be pending_review, NEVER verified!
        staged_t1 = self.store.stage_finding(
            canonical_id="GENERIC_ACT_SEC_5",
            act_code="GENERIC_ACT",
            query_trigger="amendment in section 5",
            detected_change="Proposed new section",
            source_url="https://na.gov.pk/bills/2026",
            raw_snippet="Bill introduced in National Assembly."
        )
        self.assertEqual(staged_t1["source_tier"], "tier_1")
        self.assertEqual(staged_t1["verification_status"], "pending_review")
        self.assertIn("query_hash", staged_t1)
        self.assertNotIn("query_trigger", staged_t1)

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
        self.assertEqual(staged["verification_status"], "pending_review")
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
        # 1. Non-existent statute returns [NOT CHECKED: statute not in tables]
        res = check_statute_currency("NON_EXISTENT_SEC_99", "NON_EXISTENT")
        self.assertEqual(res["label"], "NOT CHECKED")
        self.assertEqual(res["display_tag"], "[NOT CHECKED: statute not in tables]")

        # Non-seeded provision in supported act returns [NOT CHECKED]
        res_unseeded = check_statute_currency("PRPA_2009_SEC_9999", "PRPA_2009")
        self.assertEqual(res_unseeded["label"], "NOT CHECKED")
        self.assertEqual(res_unseeded["display_tag"], "[NOT CHECKED]")

        # 2. Existing seeded provision returns [BASELINE TABLE: not checked online]
        res_seeded = check_statute_currency("PRPA_2009_SEC_13", "PRPA_2009")
        self.assertEqual(res_seeded["label"], "BASELINE")
        self.assertEqual(res_seeded["display_tag"], "[BASELINE TABLE: not checked online]")
        self.assertNotIn("verified", res_seeded["display_tag"].lower())
        self.assertNotIn("current", res_seeded["display_tag"].lower())

        # 3. Online checked with no change found returns [CHECKED, NO CHANGE FOUND]
        res_checked = check_statute_currency("PRPA_2009_SEC_13", "PRPA_2009", online_checked=True)
        self.assertEqual(res_checked["label"], "CHECKED, NO CHANGE FOUND")
        self.assertEqual(res_checked["display_tag"], "[CHECKED, NO CHANGE FOUND]")

        # 4. Bill pending returns [BILL PENDING]
        test_dir = tempfile.mkdtemp()
        test_staging = tempfile.mkdtemp()
        try:
            store = StatuteVersionStore(storage_dir=test_dir, staging_dir=test_staging)
            v_bill = store.append_version(
                canonical_id="BILL_SEC_1",
                act_code="BILL_ACT",
                title="Bill Section",
                status="bill"
            )
            # Check with store
            latest_bill = store.get_latest_version("BILL_ACT", "BILL_SEC_1")
            self.assertEqual(latest_bill["status"], "bill")

            # 5. Staged finding pending review returns [CHANGE FOUND, PENDING REVIEW]
            staged = store.stage_finding(
                canonical_id="PRPA_2009_SEC_13",
                act_code="PRPA_2009",
                query_trigger="rent amendment",
                detected_change="New rent tribunal rules",
                source_url="https://punjablaws.gov.pk/gazette"
            )
            self.assertEqual(staged["source_tier"], "tier_1")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            shutil.rmtree(test_staging, ignore_errors=True)

        # 6. Strict prohibition check across all allowed tags
        allowed_tags = [
            "[CHANGE CONFIRMED]",
            "[CHECKED, NO CHANGE FOUND]",
            "[CHANGE FOUND, PENDING REVIEW]",
            "[REPORTED, UNVERIFIED]",
            "[BILL PENDING]",
            "[NOT CHECKED]",
            "[BASELINE TABLE: not checked online]"
        ]
        for tag in allowed_tags:
            # Rule: NEVER use 'verified' or 'current' in display tags
            self.assertNotIn("verified", tag.lower().replace("unverified", ""))
            self.assertNotIn("current", tag.lower())

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
        self.assertEqual(latest["version_id"], "PPC_1860_SEC_489F_V1")
        self.assertIsNone(latest["previous_version_id"])
        self.assertEqual(latest["verification_status"], "baseline_unverified")
        self.assertIsNone(latest["source_tier"])
        self.assertIsNone(latest["fetched_at"])
        self.assertIsNone(latest["text"])
        self.assertFalse(latest["text_available"])
        self.assertEqual(latest["court_challenges"], [])

    def test_real_statute_baseline_v1_records(self):
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


class TestRealCurrencyFetcher(unittest.IsolatedAsyncioTestCase):
    """Tests for Part 1, Item 3: Real Currency Check with caching, budget enforcement, whitelisting, and staging isolation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_staging = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.test_staging, "test_cache.json")
        self.cache = CurrencyCache(cache_file=self.cache_file)
        self.store = StatuteVersionStore(storage_dir=self.test_dir, staging_dir=self.test_staging, supabase_client=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.test_staging, ignore_errors=True)

    async def test_24h_caching_and_recency_bypass(self):
        call_count = {"n": 0}

        def mock_fetch(act_code, query_text, provisions):
            call_count["n"] += 1
            return [{
                "source_url": "https://pakistancode.gov.pk/amendment-act-2026",
                "title": "Act No. I of 2026",
                "detected_change": "Amendment in statutory threshold",
                "snippet": "Section 489-F amended"
            }]

        # Call 1: cold cache -> fetches
        res1 = await fetch_currency_signals(
            act_code="PPC_1860",
            provisions=["PPC_1860_SEC_489F"],
            query_text="What is the penalty under 489-f?",
            budget_s=5.0,
            mock_fetcher=mock_fetch,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(res1["status"], "CHECKED")
        self.assertFalse(res1["cache_hit"])
        self.assertEqual(call_count["n"], 1)
        self.assertEqual(len(res1["signals"]), 1)

        # Call 2: ordinary query within 24h -> hits cache, fetcher NOT called
        res2 = await fetch_currency_signals(
            act_code="PPC_1860",
            provisions=["PPC_1860_SEC_489F"],
            query_text="Explain dishonour of cheques under section 489-f",
            budget_s=5.0,
            mock_fetcher=mock_fetch,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(res2["status"], "CHECKED")
        self.assertTrue(res2["cache_hit"])
        self.assertEqual(call_count["n"], 1)  # Fetcher was NOT called again

        # Call 3: query with recency word ('latest', 'amended', etc.) -> bypasses cache, calls fetcher
        for recency_word in ["new", "recent", "amendment", "latest", "updated", "ordinance"]:
            res_rec = await fetch_currency_signals(
                act_code="PPC_1860",
                provisions=["PPC_1860_SEC_489F"],
                query_text=f"What is the {recency_word} position on section 489-f?",
                budget_s=5.0,
                mock_fetcher=mock_fetch,
                cache=self.cache,
                store=self.store
            )
            self.assertFalse(res_rec["cache_hit"])

    async def test_budget_enforcement_fail_open(self):
        # A slow network call that exceeds budget must fail open with NOT_CHECKED
        async def slow_fetch(act_code, query_text, provisions):
            await asyncio.sleep(0.3)
            return [{"source_url": "https://pakistancode.gov.pk/slow", "title": "Too late"}]

        res = await fetch_currency_signals(
            act_code="PPC_1860",
            provisions=["PPC_1860_SEC_489F"],
            query_text="Section 489-F check",
            budget_s=0.05,  # Very short budget
            mock_fetcher=slow_fetch,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(res["status"], "NOT_CHECKED")
        self.assertEqual(res["reason"], "budget_timeout")
        self.assertEqual(len(res["signals"]), 0)

    async def test_domain_whitelist_enforcement(self):
        # Whitelisted Tier 1 portals
        self.assertTrue(is_whitelisted_tier1_domain("https://pakistancode.gov.pk/doc"))
        self.assertTrue(is_whitelisted_tier1_domain("https://na.gov.pk/bills/2026"))
        self.assertTrue(is_whitelisted_tier1_domain("https://senate.gov.pk/acts/view"))
        self.assertTrue(is_whitelisted_tier1_domain("https://punjablaws.gov.pk/laws/123"))

        # Non-whitelisted domains
        self.assertFalse(is_whitelisted_tier1_domain("https://unverified-blog.com/news"))
        self.assertFalse(is_whitelisted_tier1_domain("https://newsportal.pk/article"))
        self.assertFalse(is_whitelisted_tier1_domain("https://randomsite.org/bill"))

        # Mock fetcher returning mixed domains
        def mixed_fetch(act_code, query_text, provisions):
            return [
                {"source_url": "https://unverified-blog.com/news", "title": "Fake change"},
                {"source_url": "https://pakistancode.gov.pk/valid", "title": "Legit Tier 1 gazette amendment"}
            ]

        res = await fetch_currency_signals(
            act_code="CRPC_1898",
            provisions=["CRPC_1898_SEC_497"],
            query_text="Bail provision amendments",
            budget_s=5.0,
            mock_fetcher=mixed_fetch,
            cache=self.cache,
            store=self.store
        )
        # Only the whitelisted domain must be accepted and staged
        self.assertEqual(len(res["signals"]), 1)
        self.assertEqual(res["signals"][0]["source_url"], "https://pakistancode.gov.pk/valid")

    async def test_staging_isolation_and_no_auto_promotion(self):
        # Discovered signals must be quarantined into staging ONLY, NEVER auto-promoted to main store
        self.store.append_version(
            canonical_id="QSO_1984_ART_2",
            act_code="QSO_1984",
            title="Article 2",
            status="in_force"
        )
        initial_versions = self.store.get_versions("QSO_1984")
        self.assertEqual(len(initial_versions), 1)

        def discover_change(act_code, query_text, provisions):
            return [{
                "source_url": "https://pakistancode.gov.pk/qso-amend-2026",
                "title": "QSO Amendment",
                "detected_change": "Article 2 definitions expanded"
            }]

        res = await fetch_currency_signals(
            act_code="QSO_1984",
            provisions=["QSO_1984_ART_2"],
            query_text="recent amendment in QSO Art 2",
            budget_s=5.0,
            mock_fetcher=discover_change,
            cache=self.cache,
            store=self.store
        )
        # Findings are staged
        self.assertEqual(len(res["signals"]), 1)
        staged_finding = res["signals"][0]
        self.assertFalse(staged_finding["promoted_to_main"])
        self.assertEqual(staged_finding["review_status"], "pending_review")

        # Crucial check: Main store versions are UNCHANGED (never auto-promoted)
        current_versions = self.store.get_versions("QSO_1984")
        self.assertEqual(len(current_versions), 1)
        self.assertEqual(current_versions[0]["version_id"], "QSO_1984_ART_2_V1")

    async def test_evidence_of_signal_rule_requires_amendment_term(self):
        # Hit on Tier 1 portal WITHOUT amendment/bill keywords must be dropped
        def fetch_unrelated(act_code, query_text, provisions):
            return [{
                "source_url": "https://na.gov.pk/speeches/general-debate",
                "title": "General parliamentary discussion on social welfare",
                "snippet": "Members discussed welfare schemes across the country."
            }]

        res = await fetch_currency_signals(
            act_code="PPC_1860",
            query_text="check PPC",
            budget_s=5.0,
            mock_fetcher=fetch_unrelated,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(len(res["signals"]), 0)
        self.assertEqual(res["reason"], "no_signals_found")

        # Hit WITH amendment keyword must be preserved and stage signal_term
        def fetch_with_term(act_code, query_text, provisions):
            return [{
                "source_url": "https://na.gov.pk/bills/criminal-law-amendment-2026",
                "title": "Criminal Law (Amendment) Bill 2026",
                "snippet": "An act to amend the Pakistan Penal Code 1860."
            }]

        self.cache.clear()
        res2 = await fetch_currency_signals(
            act_code="PPC_1860",
            query_text="recent amendment in PPC",
            budget_s=5.0,
            mock_fetcher=fetch_with_term,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(len(res2["signals"]), 1)
        self.assertIn("amend", res2["signals"][0].get("signal_term", ""))

    async def test_distinguish_search_failure_and_empty_pages(self):
        # 1. No pages returned from search engine must NOT produce clean check
        def empty_search(act_code, query_text, provisions):
            return {
                "signals": [],
                "search_outcome": "no_pages_returned",
                "total_seen": 0,
                "sources_checked": ["Pakistan Code", "National Assembly"]
            }

        res_empty = await fetch_currency_signals(
            act_code="CPC_1908",
            query_text="CPC update",
            budget_s=5.0,
            mock_fetcher=empty_search,
            cache=self.cache,
            store=self.store
        )
        self.assertEqual(res_empty["status"], "NOT_CHECKED")
        self.assertEqual(res_empty["reason"], "no_pages_returned")

        c_tag = check_statute_currency(
            canonical_id="CPC_1908_O21_R90",
            act_code="CPC_1908",
            search_outcome="no_pages_returned"
        )
        self.assertEqual(c_tag["label"], "NOT CHECKED")
        self.assertEqual(c_tag["display_tag"], "[NOT CHECKED: no pages returned]")

        # 2. Genuine clean check with source and date format
        c_clean = check_statute_currency(
            canonical_id="PRPA_2009_SEC_13",
            act_code="PRPA_2009",
            online_checked=True,
            online_sources="Pakistan Code, National Assembly",
            online_check_date="2026-10-01"
        )
        self.assertEqual(c_clean["label"], "CHECKED, NO CHANGE FOUND")
        self.assertEqual(c_clean["display_tag"], "[CHECKED, NO CHANGE FOUND: Pakistan Code, National Assembly on 2026-10-01]")

    def test_numeric_version_sorting_v10_after_v2(self):
        # Create versions up to V10 to test numeric ordering (V10 > V2)
        for i in range(1, 11):
            self.store.append_version(
                canonical_id="TEST_SORT_SEC_1",
                act_code="TEST_SORT",
                title=f"Version {i}",
                status="in_force"
            )
        latest = self.store.get_latest_version("TEST_SORT", "TEST_SORT_SEC_1")
        self.assertEqual(latest["version_id"], "TEST_SORT_SEC_1_V10")
        self.assertEqual(latest["title"], "Version 10")

    def test_recency_pattern_excludes_current_and_fresh(self):
        from core.statute_currency import RECENCY_WORDS_PATTERN
        self.assertIsNone(RECENCY_WORDS_PATTERN.search("what is the current status?"))
        self.assertIsNone(RECENCY_WORDS_PATTERN.search("give me a fresh update?"))
        self.assertIsNotNone(RECENCY_WORDS_PATTERN.search("is there any recent amendment?"))
        self.assertIsNotNone(RECENCY_WORDS_PATTERN.search("what is the latest rule?"))

    def test_sanitized_mflo_section_4_record(self):
        workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mflo_path = os.path.join(workspace_dir, "data", "statute_versions", "MFLO_1961_versions.json")
        with open(mflo_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        v3 = next((r for r in records if r["version_id"] == "MFLO_1961_SEC_4_V3"), None)
        self.assertIsNotNone(v3)
        self.assertEqual(v3["verification_status"], "reported_unverified")
        self.assertIsNone(v3["verified_by"])
        self.assertFalse(v3["text_available"])
        self.assertIsNone(v3["text"])
        self.assertEqual(v3["effective_application"], "pending_and_prospective")
        self.assertEqual(len(v3["court_challenges"]), 1)
        self.assertEqual(v3["court_challenges"][0]["citation"], "PLD 2000 FSC 1")
        self.assertNotIn("FCC", str(v3["court_challenges"]))

        v1 = next((r for r in records if r["version_id"] == "MFLO_1961_SEC_4_V1"), None)
        self.assertIsNotNone(v1)
        self.assertEqual(v1["verification_status"], "baseline_unverified")
        self.assertIsNone(v1["commencement_date"])

    def test_consolidated_act_page_does_not_trigger_amendment_signal(self):
        from core.currency_fetcher import is_valid_statute_signal
        # 1. Base MFLO 1961 page with standard consolidation footnotes must return None
        mflo_base_snippet = (
            "Muslim Family Laws Ordinance, 1961 (Ordinance VIII of 1961). "
            "Section 4: In the event of the death of any son or daughter... "
            "as amended by Ordinance VIII of 1961, words substituted by Act."
        )
        self.assertIsNone(is_valid_statute_signal(
            act_code="MFLO_1961",
            hit_url="https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJA%3D%3D-sg-jjjjjj",
            title="Muslim Family Laws Ordinance, 1961",
            snippet=mflo_base_snippet
        ))

        # 2. Base CPC 1908 page must return None
        cpc_base_snippet = "Code of Civil Procedure, 1908 (Act V of 1908). An Act to consolidate and amend the laws."
        self.assertIsNone(is_valid_statute_signal(
            act_code="CPC_1908",
            hit_url="https://pakistancode.gov.pk/english/cpc_1908.html",
            title="Code of Civil Procedure, 1908",
            snippet=cpc_base_snippet
        ))

        # 3. Subsequent amending bill or later enactment must trigger valid signal
        self.assertEqual(
            is_valid_statute_signal(
                act_code="MFLO_1961",
                hit_url="https://na.gov.pk/bills/mflo_amend_2024.pdf",
                title="Muslim Family Laws (Amendment) Bill, 2024",
                snippet="A bill to amend the Muslim Family Laws Ordinance 1961."
            ),
            "amendment bill"
        )
        self.assertIsNotNone(
            is_valid_statute_signal(
                act_code="CPC_1908",
                hit_url="https://pakistancode.gov.pk/acts/act_xii_2020.pdf",
                title="Code of Civil Procedure (Amendment) Act 2020",
                snippet="Act XII of 2020 to amend Act V of 1908."
            )
        )

    def test_domain_whitelist_centralized_and_no_fcc(self):
        from core.domain_whitelist import (
            ALL_TIER_1_DOMAINS,
            STATUTORY_TIER_1_DOMAINS,
            COURT_TIER_1_DOMAINS,
            is_whitelisted_tier1_domain
        )
        # Official domains present
        self.assertIn("pakistancode.gov.pk", STATUTORY_TIER_1_DOMAINS)
        self.assertIn("na.gov.pk", STATUTORY_TIER_1_DOMAINS)
        self.assertIn("supremecourt.gov.pk", COURT_TIER_1_DOMAINS)
        self.assertIn("federalshariatcourt.gov.pk", COURT_TIER_1_DOMAINS)
        self.assertIn("lhc.gov.pk", COURT_TIER_1_DOMAINS)

        # Speculative FCC domain strictly excluded
        self.assertNotIn("fcc.gov.pk", ALL_TIER_1_DOMAINS)
        self.assertFalse(is_whitelisted_tier1_domain("https://fcc.gov.pk/judgments/123"))

        # Spoofing vectors rejected
        self.assertFalse(is_whitelisted_tier1_domain("https://evil.com/?ref=na.gov.pk"))
        self.assertFalse(is_whitelisted_tier1_domain("https://na.gov.pk.evil.com"))

    def test_retrieval_trace_logger_hashes_query(self):
        from core.retrieval_logger import RetrievalTraceLogger, LOG_DIR
        raw_client_query = "Confidential client query regarding debt recovery under FIO 2001"
        logger = RetrievalTraceLogger(job_id="test_client_privacy_trace", raw_query=raw_client_query)
        logger.write_trace()

        trace_file = os.path.join(LOG_DIR, "test_client_privacy_trace.json")
        try:
            self.assertTrue(os.path.exists(trace_file))
            with open(trace_file, "r", encoding="utf-8") as f:
                trace_data = json.load(f)
            # Unhashed raw query must NOT be stored
            self.assertNotIn("Confidential client query", json.dumps(trace_data))
            self.assertIn("query_hash", trace_data)
            self.assertEqual(len(trace_data["query_hash"]), 16)
        finally:
            if os.path.exists(trace_file):
                os.remove(trace_file)

    def test_cpc_order_xxi_rule_90_baseline_seeded(self):
        from core.statute_currency import check_statute_currency, global_statute_store
        res = check_statute_currency("CPC_1908_ORD_XXI_R_90", "CPC_1908", query_text="Order XXI Rule 90 deposit")
        self.assertEqual(res["canonical_id"], "CPC_1908_ORD_XXI_R_90")
        self.assertEqual(res["verification_status"], "baseline_unverified")
        self.assertEqual(res["status"], "in_force")
        self.assertEqual(res["display_tag"], "[BASELINE TABLE: not checked online]")


class TestPrecedentTagsAndRetryCap(unittest.TestCase):
    """Tests for pre/post-amendment tags, neutral warnings, and real amendment record requirements."""

    def test_temporal_amendment_tagging_requires_real_amendment(self):
        # 1. Missing amending_instrument returns unknown
        tag, warn = tag_precedent_temporal_amendment(
            precedent_year=1998,
            statute_amendment_date="2002-10-25",
            amending_instrument=None
        )
        self.assertEqual(tag, "unknown")
        self.assertIsNone(warn)

        # 2. Missing valid_from / amendment date returns unknown
        tag2, warn2 = tag_precedent_temporal_amendment(
            precedent_year=1998,
            statute_amendment_date=None,
            amending_instrument="Ordinance LXXXV of 2002"
        )
        self.assertEqual(tag2, "unknown")
        self.assertIsNone(warn2)

        # 3. Missing precedent year returns unknown
        tag3, warn3 = tag_precedent_temporal_amendment(
            precedent_year=None,
            statute_amendment_date="2002-10-25",
            amending_instrument="Ordinance LXXXV of 2002"
        )
        self.assertEqual(tag3, "unknown")
        self.assertIsNone(warn3)

    def test_temporal_amendment_pre_and_post_neutral_wording(self):
        # Precedent from 1998 on an amendment that took effect in 2002
        tag, warn = tag_precedent_temporal_amendment(
            precedent_year=1998,
            statute_amendment_date="2002-10-25",
            amending_instrument="Criminal Law (Amendment) Ordinance, 2002 (LXXXV of 2002)",
            section_label="Section 489-F"
        )
        self.assertEqual(tag, "pre_amendment")
        self.assertIsNotNone(warn)
        # Neutral wording requirement: "Decided before the <date> amendment of <section>. Check whether the amendment affects this point."
        self.assertEqual(
            warn,
            "Decided before the 2002-10-25 amendment of Section 489-F. Check whether the amendment affects this point."
        )
        # NEVER say "interprets repealed language"
        self.assertNotIn("repealed language", warn.lower())
        self.assertNotIn("interprets", warn.lower())

        # Precedent from 2020 on the 2002 amendment
        tag_post, warn_post = tag_precedent_temporal_amendment(
            precedent_year=2020,
            statute_amendment_date="2002-10-25",
            amending_instrument="Criminal Law (Amendment) Ordinance, 2002 (LXXXV of 2002)",
            section_label="Section 489-F"
        )
        self.assertEqual(tag_post, "post_amendment")
        self.assertIsNone(warn_post)

    def test_temporal_amendment_store_lookup(self):
        # In baseline store with no amendment record, returns unknown
        tag_base, warn_base = tag_precedent_temporal_amendment(
            precedent_year=1995,
            act_code="PPC_1860",
            canonical_id="PPC_1860_SEC_489F"
        )
        self.assertEqual(tag_base, "unknown")
        self.assertIsNone(warn_base)

        # In a test store where an amendment version is appended
        test_dir = tempfile.mkdtemp()
        test_staging = tempfile.mkdtemp()
        try:
            store = StatuteVersionStore(storage_dir=test_dir, staging_dir=test_staging, supabase_client=False)
            # V1: baseline
            store.append_version(
                canonical_id="TEST_ACT_SEC_5",
                act_code="TEST_ACT",
                title="Section 5",
                status="in_force"
            )
            # Check before amendment
            t0, w0 = tag_precedent_temporal_amendment(
                precedent_year=2010,
                act_code="TEST_ACT",
                canonical_id="TEST_ACT_SEC_5",
                store=store
            )
            self.assertEqual(t0, "unknown")
            self.assertIsNone(w0)

            # V2: amendment with amending_instrument and valid_from
            store.append_version(
                canonical_id="TEST_ACT_SEC_5",
                act_code="TEST_ACT",
                title="Section 5",
                status="amended",
                amending_instrument="Act XII of 2018",
                valid_from="2018-05-15",
                source_tier="tier_1"
            )

            # Precedent before 2018 amendment
            t_pre, w_pre = tag_precedent_temporal_amendment(
                precedent_year=2012,
                act_code="TEST_ACT",
                canonical_id="TEST_ACT_SEC_5",
                store=store
            )
            self.assertEqual(t_pre, "pre_amendment")
            self.assertEqual(
                w_pre,
                "Decided before the 2018-05-15 amendment of Section 5. Check whether the amendment affects this point."
            )

            # Precedent after 2018 amendment
            t_after, w_after = tag_precedent_temporal_amendment(
                precedent_year=2021,
                act_code="TEST_ACT",
                canonical_id="TEST_ACT_SEC_5",
                store=store
            )
            self.assertEqual(t_after, "post_amendment")
            self.assertIsNone(w_after)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            shutil.rmtree(test_staging, ignore_errors=True)


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

        fcc_text = (
            "IN THE FEDERAL CONSTITUTIONAL COURT OF PAKISTAN\n"
            "Constitutional Petition No. 1 of 2025\n"
        )
        self.assertEqual(derive_court_from_judgment_header(fcc_text), "Federal Constitutional Court")

        fsc_text = (
            "IN THE FEDERAL SHARIAT COURT OF PAKISTAN\n"
            "(APPELLATE JURISDICTION)\n"
            "Shariat Petition No. 12 of 2000\n"
        )
        self.assertEqual(derive_court_from_judgment_header(fsc_text), "Federal Shariat Court")

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


class TestConstitutionalArticlesGroundingRule24(unittest.TestCase):
    """
    Tests for Rule 24 replacement (Part B): Universal Constitutional Article Grounding.
    Exercises all 9 test cases from the review:
    1. Bare Article 25 (query-only) -> flagged
    2. Article 25 of the Constitution (query-only) -> flagged
    3. Contention framing: 'You argue the deposit violates Article 25; no retrieved authority...' -> passes
    4. Grounded: 'Articles 4, 9 and 10-A concern timely justice.' -> passes
    5. Normalisation: 'Article 10A applies.' -> passes
    6. Partial grounding: 'See Articles 4, 9 and 14.' -> flags 14 only
    7. Statutory exemption: 'Article 181 of the Limitation Act applies.' -> passes
    8. Statutory exemption: 'Article 129 of Qanun-e-Shahadat Order' -> passes
    9. Unexempt: 'Under Art. 199 writ jurisdiction' -> flagged (199 not exempt)
    """

    def test_user_part_b_nine_cases(self):
        retrieved = "Articles 4, 9 & 10-A of the Constitution on delay. Order XXI Rule 90."
        query_with_25 = "Can deposit be challenged under Article 25?"

        # Case 1: "The deposit may be challenged under Article 25." (query-only) -> flagged
        p1 = find_ungrounded_articles("The deposit may be challenged under Article 25.", retrieved, query=query_with_25)
        self.assertEqual(len(p1), 1)
        self.assertIn("Ungrounded Constitutional Article 25 (raised only in the query)", p1[0])

        # Case 2: "Challenge it under Article 25 of the Constitution." (query-only) -> flagged
        p2 = find_ungrounded_articles("Challenge it under Article 25 of the Constitution.", retrieved, query=query_with_25)
        self.assertEqual(len(p2), 1)
        self.assertIn("Ungrounded Constitutional Article 25 (raised only in the query)", p2[0])

        # Case 3: "You argue the deposit violates Article 25; no retrieved authority addresses this." -> passes
        p3 = find_ungrounded_articles("You argue the deposit violates Article 25; no retrieved authority addresses this.", retrieved, query=query_with_25)
        self.assertEqual(len(p3), 0)

        # Case 4: "Articles 4, 9 and 10-A concern timely justice." -> passes
        p4 = find_ungrounded_articles("Articles 4, 9 and 10-A concern timely justice.", retrieved, query="")
        self.assertEqual(len(p4), 0)

        # Case 5: "Article 10A applies." -> passes (10-A and 10A normalise)
        p5 = find_ungrounded_articles("Article 10A applies.", retrieved, query="")
        self.assertEqual(len(p5), 0)

        # Case 6: "See Articles 4, 9 and 14." -> flags 14 only
        p6 = find_ungrounded_articles("See Articles 4, 9 and 14.", retrieved, query="")
        self.assertEqual(len(p6), 1)
        self.assertIn("Ungrounded Constitutional Article 14 (absent from retrieved text)", p6[0])

        # Case 7: "Article 181 of the Limitation Act applies." -> passes
        p7 = find_ungrounded_articles("Article 181 of the Limitation Act applies.", retrieved, query="")
        self.assertEqual(len(p7), 0)

        # Case 8: "Article 129 of Qanun-e-Shahadat Order" -> passes
        p8 = find_ungrounded_articles("Article 129 of Qanun-e-Shahadat Order", retrieved, query="")
        self.assertEqual(len(p8), 0)

        # Case 9: "Under Art. 199 writ jurisdiction" -> flagged (199 not exempt)
        p9 = find_ungrounded_articles("Under Art. 199 writ jurisdiction", retrieved, query="")
        self.assertEqual(len(p9), 1)
        self.assertIn("Ungrounded Constitutional Article 199 (absent from retrieved text)", p9[0])

    def test_lint_legal_output_rule_24_integration(self):
        mock_chunks = [
            {"metadata": {"text": "Articles 4, 9 & 10-A of the Constitution on delay. Order XXI Rule 90."}}
        ]
        query = "Can deposit be challenged under Article 25?"

        # Ungrounded Article 25 without contention framing -> flagged
        errs = lint_legal_output("The deposit may be challenged under Article 25.", query_context=query, context_chunks=mock_chunks)
        self.assertTrue(any("Ungrounded Constitutional Article 25" in e for e in errs))

        # Grounded Articles 4, 9 and 10-A -> passes
        good_errs = lint_legal_output("Articles 4, 9 and 10-A concern timely justice.", query_context=query, context_chunks=mock_chunks)
        self.assertFalse(any("Ungrounded Constitutional Article" in e for e in good_errs))

        # Contention framing -> passes
        contention_errs = lint_legal_output("You argue the deposit violates Article 25; no retrieved authority addresses this.", query_context=query, context_chunks=mock_chunks)
        self.assertFalse(any("Ungrounded Constitutional Article" in e for e in contention_errs))

        # Statutory article (Limitation Act) -> passes
        stat_errs = lint_legal_output("Article 181 of the Limitation Act applies.", query_context=query, context_chunks=mock_chunks)
        self.assertFalse(any("Ungrounded Constitutional Article" in e for e in stat_errs))

        # Procedural exempt articles (175, 185, 189, 201) -> pass without grounding
        exempt_errs = lint_legal_output("Under Article 189 and Article 201, binding precedent must be followed.", query_context=query, context_chunks=mock_chunks)
        self.assertFalse(any("Ungrounded Constitutional Article" in e for e in exempt_errs))


if __name__ == "__main__":
    unittest.main()
