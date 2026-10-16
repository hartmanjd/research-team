"""Tests for the website's JSON API, on the small made-up database from the dashboard tests.

Run from the repo root:  python3 -m unittest discover web/tests
"""
import os, sys, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "dashboard", "tests"))
from test_queries import make_db  # noqa: E402
from web import api  # noqa: E402


class ApiTests(unittest.TestCase):
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

    def acme_tx(self):
        hits = self.client.get("/api/search", params={"q": "acme software"}).json()
        return next(h for h in hits if h["state"] == "TX" and h["program"] == "H-1B")

    def test_search(self):
        names = [h["employer_name"] for h in self.client.get("/api/search", params={"q": "acme"}).json()]
        self.assertIn("Acme Analytics", names)
        self.assertEqual(self.client.get("/api/search", params={"q": ""}).json(), [])

    def test_employer_page_data(self):
        d = self.client.get(f"/api/employers/{self.acme_tx()['employer_id']}").json()
        self.assertEqual(d["summary"]["cases"], 2)
        self.assertEqual([c["case_id"] for c in d["cases"]], [11, 10])
        self.assertTrue(d["cases"][0]["match_label"].startswith("Matched by clean name + state"))
        self.assertEqual([(r["program"], r["state"]) for r in d["same_tax_id"]], [("H-1B", "CA"), ("H-2B", "TX")])
        self.assertEqual(self.client.get("/api/employers/999999").status_code, 404)

    def test_applications_are_paged(self):
        eid = self.acme_tx()["employer_id"]
        with mock.patch.object(api, "PAGE_SIZE", 1):
            p1 = self.client.get(f"/api/employers/{eid}/applications").json()
            p2 = self.client.get(f"/api/employers/{eid}/applications", params={"page": 2}).json()
        self.assertEqual((p1["total"], len(p1["rows"]), p1["rows"][0]["case_number"]), (2, 1, "I-1"))
        self.assertEqual(p2["rows"][0]["case_number"], "I-2")
        self.assertTrue(p1["rows"][0]["dol_file_url"])
        self.assertEqual(self.client.get("/api/employers/999999/applications").status_code, 404)

    def test_watchlist_and_filters(self):
        d = self.client.get("/api/watchlist").json()
        self.assertEqual([r["program"] for r in d["rows"]], ["H-1B", "H-2B"])
        self.assertEqual(d["totals"]["cases"], 2)
        d = self.client.get("/api/watchlist", params={"program": "H-1B", "since": 2020}).json()
        self.assertEqual([(r["program"], r["n_cases"]) for r in d["rows"]], [("H-1B", 1)])
        d = self.client.get("/api/watchlist", params={"visa_only": "true"}).json()
        self.assertEqual([r["program"] for r in d["rows"]], ["H-1B"])
        self.assertEqual(self.client.get("/api/watchlist", params={"program": "H-3"}).status_code, 422)

    def test_meta_and_site(self):
        self.assertIn("TX", self.client.get("/api/meta").json()["states"])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Visa Employer Watch", page.text)
        self.assertEqual(self.client.get("/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
