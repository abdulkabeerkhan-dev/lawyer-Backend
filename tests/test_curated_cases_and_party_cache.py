import unittest
import time
from core.curated_cases import find_curated_case, is_curated_historical_exception, get_curated_cases
from core.party_cache import PartyFallbackCache

class TestCuratedCasesAndPartyCache(unittest.TestCase):
    def test_curated_cases_loaded(self):
        cases = get_curated_cases()
        self.assertGreaterEqual(len(cases), 3)
        case_ids = [c["case_id"] for c in cases]
        self.assertIn("1958_PLD_SC_533", case_ids)
        self.assertIn("1958_PLD_SC_138", case_ids)
        self.assertIn("2013_SCMR_51", case_ids)

    def test_find_curated_case_by_citation_and_alias(self):
        # Exact citation match
        c1 = find_curated_case(citation="PLD 1958 SC 533")
        self.assertIsNotNone(c1)
        self.assertEqual(c1["case_title"], "State v. Dosso")

        # Normalized case_id match
        c2 = find_curated_case(case_id="1958_PLD_SC_138")
        self.assertIsNotNone(c2)
        self.assertIn("Muralidhar", c2["case_title"])

        # Alias / keyword match
        c3 = find_curated_case(text="What did the court hold in State v. Dosso regarding doctrine of revolutionary legality?")
        self.assertIsNotNone(c3)
        self.assertEqual(c3["precedent_status"], "overruled")

        # 2013 SCMR 51 match
        c4 = find_curated_case(citation="2013 SCMR 51")
        self.assertIsNotNone(c4)
        self.assertEqual(c4["court_name"], "Supreme Court of Pakistan")

    def test_is_curated_historical_exception(self):
        self.assertTrue(is_curated_historical_exception(year=1958, page=533, journal="PLD"))
        self.assertTrue(is_curated_historical_exception(year=1958, page=138, journal="PLD"))
        self.assertFalse(is_curated_historical_exception(year=2013, page=51, journal="SCMR"))
        self.assertFalse(is_curated_historical_exception(year=1955, page=240, journal="PLD"))

    def test_party_cache_ttl_and_hit(self):
        cache = PartyFallbackCache(default_ttl_seconds=10.0)
        party = "Mian Allah Ditta"
        data = {"case_id": "2013_SCMR_51", "neutral_citation": "2013 SCMR 51", "title": "Mian Allah Ditta v. State"}

        t0 = 1000.0
        cache.set(party, data, citation="2013 SCMR 51", current_time=t0)

        # Hit within TTL
        hit, res = cache.get(party, citation="2013 SCMR 51", current_time=t0 + 5.0)
        self.assertTrue(hit)
        self.assertEqual(res["case_id"], "2013_SCMR_51")

        # Miss after TTL
        hit_expired, res_expired = cache.get(party, citation="2013 SCMR 51", current_time=t0 + 15.0)
        self.assertFalse(hit_expired)
        self.assertIsNone(res_expired)

    def test_party_cache_cross_case_isolation(self):
        """
        Verify that a cached party-name fallback result for Case A cannot attach
        to a query for a different Case B, even with the exact same party name.
        """
        cache = PartyFallbackCache(default_ttl_seconds=3600.0)
        party = "Federation of Pakistan"
        case_a = {
            "case_id": "2010_SCMR_1",
            "neutral_citation": "2010 SCMR 1",
            "title": "Federation of Pakistan v. Shaukat Ali"
        }

        # Store record for Case A
        cache.set(party, case_a, citation="2010 SCMR 1", case_id="2010_SCMR_1")

        # Query with same party and matching citation -> HIT
        hit_same, res_same = cache.get(party, citation="2010 SCMR 1")
        self.assertTrue(hit_same)
        self.assertEqual(res_same["case_id"], "2010_SCMR_1")

        # Query with same party but DIFFERENT citation -> ISOLATION ENFORCED (MISS)
        hit_diff, res_diff = cache.get(party, citation="2024 SCMR 999")
        self.assertFalse(hit_diff, "Cross-case pollution detected: Case A attached to Case B query!")
        self.assertIsNone(res_diff)

        # Query with different case_id -> ISOLATION ENFORCED (MISS)
        hit_diff_cid, res_diff_cid = cache.get(party, case_id="2022_PLD_SC_500")
        self.assertFalse(hit_diff_cid, "Cross-case pollution detected: wrong case_id attached!")
        self.assertIsNone(res_diff_cid)


class TestStatuteVersionStoreSupabase(unittest.TestCase):
    def test_version_store_with_mock_supabase(self):
        from tests.mock_supabase import MockSupabaseClient
        from core.statute_currency import StatuteVersionStore
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        try:
            mock_sb = MockSupabaseClient()
            store = StatuteVersionStore(storage_dir=temp_dir, staging_dir=temp_dir, supabase_client=mock_sb)

            # 1. Batch import initial versions
            provisions = [
                {"canonical_id": "MFLO_1961_S4", "title": "Succession", "primary_num": "4", "provision_type": "section"}
            ]
            count = store.batch_import_initial_versions("MFLO_1961", provisions)
            self.assertEqual(count, 1)

            # Check that mock DB table received the row
            sb_rows = mock_sb.table("statute_versions").select("*").eq("canonical_id", "MFLO_1961_S4").execute().data
            self.assertEqual(len(sb_rows), 1)
            self.assertEqual(sb_rows[0]["verification_status"], "baseline_unverified")

            # 2. Append new version
            v2 = store.append_version(
                canonical_id="MFLO_1961_S4",
                act_code="MFLO_1961",
                title="Succession",
                status="declared_repugnant_appeal_pending",
                source_url="https://pakistancode.gov.pk/sample",
                verification_status="verified"
            )
            self.assertEqual(v2["status"], "declared_repugnant_appeal_pending")

            # Query latest version via store
            latest = store.get_latest_version("MFLO_1961", "MFLO_1961_S4")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["status"], "declared_repugnant_appeal_pending")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
