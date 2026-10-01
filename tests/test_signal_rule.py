import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.signal_rule import SignalContext, evaluate_signal, instrument_key, roman_to_int

def ctx_mflo(**kw):
    base = dict(act_code="MFLO_1961", since_year=2025, last_checked=date(2026, 9, 1),
                base_titles=["Muslim Family Laws Ordinance, 1961", "Muslim Family Laws Ordinance 1961"],
                base_instruments={instrument_key("ordinance", "VIII", 1961)})
    base.update(kw)
    return SignalContext(**base)

def ctx_cpc(**kw):
    base = dict(act_code="CPC_1908", since_year=2025, base_titles=["Code of Civil Procedure, 1908",
                "Code of Civil Procedure 1908"], base_instruments={instrument_key("act", "V", 1908)})
    base.update(kw)
    return SignalContext(**base)

class TestNoSignal(unittest.TestCase):
    def test_consolidated_mflo_page_has_no_signal(self):
        hit = {"url": "https://pakistancode.gov.pk/x", "title": "The Muslim Family Laws Ordinance, 1961 (Ordinance VIII of 1961)",
               "snippet": "Section 4 omitted; substituted by Ordinance XXV of 1981; amended by Act VI of 1985. Ordinance"}
        r = evaluate_signal(hit, ctx_mflo())
        self.assertFalse(r["is_signal"], r)

    def test_cpc_page_listing_old_amendments_has_no_signal(self):
        hit = {"url": "https://pakistancode.gov.pk/cpc", "title": "Code of Civil Procedure, 1908",
               "snippet": "Amended by Act II of 1976, Ordinance X of 1980 and Act XXIV of 1992. Rule 90 substituted."}
        self.assertFalse(evaluate_signal(hit, ctx_cpc())["is_signal"])

    def test_generic_words_alone_are_not_a_signal(self):
        hit = {"url": "https://na.gov.pk/p", "title": "Amended omitted substituted repealed bill ordinance", "snippet": ""}
        self.assertFalse(evaluate_signal(hit, ctx_cpc())["is_signal"])

    def test_known_instrument_not_repeated(self):
        k = instrument_key("act", "IV", 2026)
        hit = {"url": "https://na.gov.pk/a", "title": "Act IV of 2026", "snippet": "amends the Code of Civil Procedure"}
        self.assertTrue(evaluate_signal(hit, ctx_cpc())["is_signal"])
        self.assertFalse(evaluate_signal(hit, ctx_cpc(known_instruments={k}))["is_signal"])

    def test_known_url_skipped(self):
        hit = {"url": "https://na.gov.pk/a", "title": "Act IV of 2026", "snippet": ""}
        self.assertFalse(evaluate_signal(hit, ctx_cpc(known_urls={"https://na.gov.pk/a"}))["is_signal"])

    def test_page_older_than_last_check_ignored(self):
        hit = {"url": "https://na.gov.pk/a", "title": "Ordinance III of 2025", "snippet": "", "date": "2025-03-01"}
        c = ctx_cpc(last_checked=date(2026, 9, 1))
        self.assertFalse(evaluate_signal(hit, c)["is_signal"])

    def test_lowercase_roman_lookalikes_do_not_match(self):
        hit = {"url": "https://na.gov.pk/a", "title": "Act mid of 2026", "snippet": "ordinance dim of 2026"}
        self.assertFalse(evaluate_signal(hit, ctx_cpc())["is_signal"])

class TestSignal(unittest.TestCase):
    def test_new_amendment_ordinance_is_signal(self):
        hit = {"url": "https://pakistancode.gov.pk/n", "title": "Civil Procedure Code (Amendment) Ordinance, 2026",
               "snippet": "promulgated and notified in the Gazette", "date": "2026-09-28"}
        r = evaluate_signal(hit, ctx_cpc(last_checked=date(2026, 9, 1)))
        self.assertTrue(r["is_signal"])
        self.assertEqual(r["stage_hint"], "notified")

    def test_new_bill_is_bill_not_law(self):
        hit = {"url": "https://na.gov.pk/bills/55", "title": "The Muslim Family Laws (Amendment) Bill, 2026",
               "snippet": "introduced in the National Assembly"}
        r = evaluate_signal(hit, ctx_mflo())
        self.assertTrue(r["is_signal"])
        self.assertEqual(r["kind"], "bill")

    def test_roman_numeral_instrument_with_year_is_signal(self):
        hit = {"url": "https://na.gov.pk/a", "title": "Act XII of 2026", "snippet": "assent received"}
        r = evaluate_signal(hit, ctx_cpc())
        self.assertTrue(r["is_signal"])
        self.assertEqual(r["instrument_keys"], ["act:12:2026"])
        self.assertEqual(r["stage_hint"], "assented")

    def test_base_instrument_never_counts_even_if_recent(self):
        c = SignalContext("NEW_ACT_2026", since_year=2025, base_instruments={instrument_key("act", "III", 2026)})
        hit = {"url": "https://na.gov.pk/a", "title": "Act III of 2026", "snippet": ""}
        self.assertFalse(evaluate_signal(hit, c)["is_signal"])

    def test_helpers(self):
        self.assertEqual(roman_to_int("XLVI"), 46)
        self.assertEqual(roman_to_int("MCMLXI"), 1961)
        self.assertEqual(instrument_key("Ordinance", "XLVI", 2001), "ordinance:46:2001")

if __name__ == "__main__":
    unittest.main()
