import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import search_provider as sp

HOSTS = ["pakistancode.gov.pk", "na.gov.pk", "lhc.gov.pk"]

def gcse(items):
    return json.dumps({"items": items})

def item(url, title="t", snippet="s"):
    return {"title": title, "link": url, "snippet": snippet}

class FakeHttp:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0
    def __call__(self, url, headers, timeout):
        self.calls += 1
        r = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

def mk(http, **kw):
    return sp.GoogleCSEProvider("k", "cx", HOSTS, http, **kw)

class TestStatuses(unittest.TestCase):
    def test_ok_and_parse(self):
        r = mk(FakeHttp((200, gcse([item("https://na.gov.pk/bills/1")]))))\
            .search("Muslim Family Laws Ordinance 1961 amendment")
        self.assertEqual(r.status, sp.OK)
        self.assertEqual(r.results[0]["url"], "https://na.gov.pk/bills/1")

    def test_empty_is_not_ok(self):
        r = mk(FakeHttp((200, json.dumps({})))).search("x")
        self.assertEqual(r.status, sp.EMPTY)
        self.assertEqual(sp.to_outcome(r)["state"], "no_pages_returned")

    def test_429_rate_limited(self):
        self.assertEqual(mk(FakeHttp((429, ""))).search("x").status, sp.RATE_LIMITED)

    def test_403_blocked_and_quota_variant(self):
        self.assertEqual(mk(FakeHttp((403, "forbidden"))).search("x").status, sp.BLOCKED)
        self.assertEqual(mk(FakeHttp((403, '{"error":{"errors":[{"reason":"dailyLimitExceeded"}]}}'))).search("x").status,
                         sp.RATE_LIMITED)

    def test_duckduckgo_style_challenge_page_is_blocked_not_empty(self):
        html = "<html><body><div class='anomaly-modal'>Bot-detection challenge</div></body></html>"
        r = mk(FakeHttp((202, html))).search("x")
        self.assertEqual(r.status, sp.BLOCKED)
        self.assertEqual(sp.to_outcome(r)["state"], "search_failed")
        r2 = mk(FakeHttp((200, html))).search("x")
        self.assertEqual(r2.status, sp.BLOCKED)

    def test_timeout_and_5xx_failed(self):
        self.assertEqual(mk(FakeHttp(TimeoutError())).search("x").status, sp.FAILED)
        self.assertEqual(mk(FakeHttp((503, ""))).search("x").status, sp.FAILED)

    def test_parse_error_failed(self):
        self.assertEqual(mk(FakeHttp((200, "not json"))).search("x").status, sp.FAILED)

class TestHostFiltering(unittest.TestCase):
    def test_spoofed_and_off_domain_results_dropped(self):
        items = [item("https://evil.com/?ref=na.gov.pk"), item("https://na.gov.pk.evil.com/x"),
                 item("https://blog.example.com/pakistancode.gov.pk-amendment"),
                 item("https://www.lhc.gov.pk/judgment/1")]
        r = mk(FakeHttp((200, gcse(items)))).search("x")
        self.assertEqual([x["url"] for x in r.results], ["https://www.lhc.gov.pk/judgment/1"])
        self.assertEqual(r.dropped_off_domain, 3)

    def test_all_off_domain_becomes_empty(self):
        r = mk(FakeHttp((200, gcse([item("https://evil.com/na.gov.pk")])))).search("x")
        self.assertEqual(r.status, sp.EMPTY)

class TestGuards(unittest.TestCase):
    def test_circuit_opens_then_short_circuits_without_http(self):
        http = FakeHttp((503, ""))
        now = [0.0]
        p = mk(http, failure_threshold=3, cooldown_s=300, clock=lambda: now[0])
        for _ in range(3):
            self.assertEqual(p.search("x").status, sp.FAILED)
        calls = http.calls
        self.assertEqual(p.search("x").status, sp.CIRCUIT_OPEN)
        self.assertEqual(http.calls, calls)
        now[0] = 301.0
        http.responses = [(200, gcse([item("https://na.gov.pk/a")]))]
        self.assertEqual(p.search("x").status, sp.OK)

    def test_daily_cap_and_reset(self):
        day = ["2026-10-02"]
        p = mk(FakeHttp((200, gcse([item("https://na.gov.pk/a")]))), daily_cap=2, today=lambda: day[0])
        self.assertEqual(p.search("a").status, sp.OK)
        self.assertEqual(p.search("b").status, sp.OK)
        self.assertEqual(p.search("c").status, sp.QUOTA_EXHAUSTED)
        day[0] = "2026-10-03"
        self.assertEqual(p.search("d").status, sp.OK)

    def test_success_resets_failure_count(self):
        http = FakeHttp((503, ""), (503, ""), (200, gcse([item("https://na.gov.pk/a")])), (503, ""), (503, ""))
        p = mk(http, failure_threshold=3)
        for _ in range(5):
            p.search("x")
        self.assertNotEqual(p.search("x").status, sp.CIRCUIT_OPEN)

class TestConfig(unittest.TestCase):
    def test_unconfigured_is_explicit(self):
        p = sp.build_provider_from_env({}, HOSTS)
        r = p.search("x")
        self.assertEqual(r.status, sp.NOT_CONFIGURED)
        self.assertEqual(sp.to_outcome(r)["state"], "search_failed")

    def test_env_selection(self):
        env = {"SEARCH_PROVIDER": "google_cse", "GOOGLE_CSE_KEY": "k", "GOOGLE_CSE_CX": "c"}
        self.assertIsInstance(sp.build_provider_from_env(env, HOSTS), sp.GoogleCSEProvider)
        env = {"SEARCH_PROVIDER": "searxng", "SEARXNG_URL": "http://localhost:8080"}
        self.assertIsInstance(sp.build_provider_from_env(env, HOSTS), sp.SearxNGProvider)
        self.assertIsInstance(sp.build_provider_from_env({"SEARCH_PROVIDER": "google_cse"}, HOSTS),
                              sp.UnconfiguredProvider)

    def test_searxng_parse(self):
        body = json.dumps({"results": [{"url": "https://na.gov.pk/b", "title": "T", "content": "C",
                                        "publishedDate": "2026-09-01"}]})
        r = sp.SearxNGProvider("http://s", HOSTS, FakeHttp((200, body))).search("x")
        self.assertEqual(r.status, sp.OK)
        self.assertEqual(r.results[0]["date"], "2026-09-01")

    def test_query_is_scoped_but_filter_is_the_control(self):
        seen = {}
        def http(url, headers, timeout):
            seen["url"] = url
            return 200, gcse([item("https://na.gov.pk/a")])
        mk(http).search("Civil Procedure Code amendment")
        self.assertIn("site%3Ana.gov.pk", seen["url"])

if __name__ == "__main__":
    unittest.main()
