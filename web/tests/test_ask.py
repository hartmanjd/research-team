"""Tests for the Ask endpoints and their limits, with a scripted stand-in for the model (no API calls).

Run from the repo root:  python3 -m unittest discover web/tests
"""
import json, os, sys, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "dashboard", "tests"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "chat", "tests"))
from test_chat import FakeClient, call, reply, text  # noqa: E402
from test_queries import make_db  # noqa: E402
from chat import limits  # noqa: E402
from web import api  # noqa: E402


class AskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, {"RESEARCH_DB": make_db(tempfile.mkdtemp())})
        cls.env.start()
        cls.client = TestClient(api.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.env.stop()

    def setUp(self):
        api.spend = limits.SpendCap(cap_usd=1.0)
        api.rate = limits.RateLimit(per_minute=5, per_day=40)
        api._client = None

    def ask(self, question="Who is Acme?", history=(), ip="1.2.3.4"):
        r = self.client.post("/api/ask", json={"question": question, "history": list(history)},
                             headers={"X-Forwarded-For": f"{ip}, 10.0.0.1"})
        return r, [json.loads(line) for line in r.text.splitlines()] if r.status_code == 200 else []

    def test_streams_lookups_then_the_answer(self):
        api._client = fake = FakeClient(reply(call(1, "search_employers", {"query": "acme"})),
                                        reply(text("Acme Analytics has no cases.")))
        self.assertEqual(self.client.get("/api/ask").json()["enabled"], True)
        r, events = self.ask(history=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}])
        self.assertEqual(r.headers["content-type"], "application/x-ndjson")
        self.assertEqual([e["type"] for e in events], ["tool", "answer"])
        self.assertEqual(events[0]["name"], "search_employers")
        self.assertEqual(events[1]["raw"], "Acme Analytics has no cases.")
        self.assertEqual([m["content"] for m in fake.requests[0]["messages"]][:2], ["Hi", "Hello"])
        self.assertGreater(api.spend.spent, 0)
        self.assertEqual(api.spend.held, 0)

    def test_rejects_bad_input(self):
        api._client = FakeClient()
        self.assertEqual(self.ask("")[0].status_code, 422)
        self.assertEqual(self.ask("x" * 601)[0].status_code, 422)
        self.assertEqual(self.ask(history=[{"role": "user", "content": "a"}])[0].status_code, 422)
        self.assertEqual(self.ask(history=[{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])[0]
                         .status_code, 422)

    def test_needs_a_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(self.client.get("/api/ask").json(), {"enabled": False, "reason": "not_set_up"})
            self.assertEqual(self.ask()[0].status_code, 503)

    def test_rate_limit_per_visitor(self):
        api._client = FakeClient(*[reply(text("ok")) for _ in range(6)])
        api.rate = limits.RateLimit(per_minute=2, per_day=40)
        self.assertEqual([self.ask(ip="5.5.5.5")[0].status_code for _ in range(3)], [200, 200, 429])
        self.assertEqual(self.ask(ip="6.6.6.6")[0].status_code, 200)  # another visitor is not held up

    def test_daily_cap(self):
        api._client = FakeClient(reply(text("ok")))
        api.spend = limits.SpendCap(cap_usd=0.03)
        api.spend.settle(0.02, amount=0)
        self.assertEqual(self.client.get("/api/ask").json()["reason"], "daily_limit")
        r, _ = self.ask()
        self.assertEqual(r.status_code, 503)
        self.assertIn("budget", r.json()["detail"])

    def test_api_failure_becomes_an_error_line(self):
        class Broken:
            messages = None
        api._client = Broken()
        _, events = self.ask()
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(api.spend.held, 0)


class LimitTests(unittest.TestCase):
    def test_spend_cap_resets_each_day_and_survives_a_restart(self):
        day, path = ["2026-10-16"], os.path.join(tempfile.mkdtemp(), "spend.json")
        cap = limits.SpendCap(cap_usd=0.05, path=path, clock=lambda: day[0])
        self.assertTrue(cap.reserve(0.02))
        self.assertTrue(cap.reserve(0.02))
        self.assertFalse(cap.reserve(0.02))  # two held questions plus a third would pass the cap
        cap.settle(0.001, 0.02)
        cap.settle(0.001, 0.02)
        self.assertAlmostEqual(limits.SpendCap(cap_usd=0.05, path=path, clock=lambda: day[0]).spent, 0.002)
        day[0] = "2026-10-17"
        self.assertAlmostEqual(cap.left(), 0.05)

    def test_rate_limit_windows(self):
        now = [0.0]
        rl = limits.RateLimit(per_minute=2, per_day=3, clock=lambda: now[0])
        self.assertEqual([rl.check("a") is None for _ in range(3)], [True, True, False])
        now[0] = 61
        self.assertIsNone(rl.check("a"))
        self.assertIn("tomorrow", rl.check("a"))
        now[0] = 86400 + 62
        self.assertIsNone(rl.check("a"))


if __name__ == "__main__":
    unittest.main()
