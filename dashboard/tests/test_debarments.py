"""Tests for matching DOL debarment entries to visa employers, and for the list parser's helpers.

Run from the repo root:  python3 -m unittest discover dashboard/tests
"""
import csv, datetime, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "h1b-data", "scripts"))
sys.path.insert(0, HERE)
import parse_debarments, queries  # noqa: E402
from test_queries import make_db  # noqa: E402

TODAY = datetime.date(2026, 10, 16)


def write_debarments(path, entries):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, parse_debarments.FIELDS)
        w.writeheader()
        for e in entries:
            row = {k: "" for k in parse_debarments.FIELDS}
            row.update(e, name_clean=parse_debarments.clean_name(e["entity"]), source_url="https://example.gov/d")
            w.writerow(row)


class DebarmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        cls.con = queries.connect(make_db(d))
        cls.csv = os.path.join(d, "debarments.csv")
        write_debarments(cls.csv, [
            # Same name in Texas: matches the TX rows only.
            {"program": "H-2B", "entity": "Acme Software, Inc.*", "state": "TX", "location": "Austin, Texas",
             "start_date": "2025-01-01", "end_date": "2028-01-01", "violation": "WHD Debarment"},
            # No address (DOL's H-1B list): matches on name alone, in any state. Ended.
            {"program": "H-1B", "entity": "Widget Co d/b/a Acme Analytics", "start_date": "2020-01-01",
             "end_date": "2022-01-01"},
            {"program": "H-2A", "entity": "Nobody Farms LLC", "state": "FL", "start_date": "",
             "end_date": "permanent"},
        ])
        queries.load_debarments.cache_clear()
        hits = {(h["employer_name"], h["state"]): h["employer_id"] for h in queries.search_employers(cls.con, "acme")}
        cls.acme_tx = next(i for (name, st), i in hits.items() if st == "TX")
        cls.acme_ca = next(i for (name, st), i in hits.items() if st == "CA")
        cls.analytics = next(i for (name, st), i in hits.items() if name == "Acme Analytics")

    def test_name_and_state_match(self):
        tx = queries.employer_debarments(self.con, self.acme_tx, path=self.csv, today=TODAY)
        self.assertEqual([(d["program"], d["status"]) for d in tx], [("H-2B", "active")])
        self.assertIn("state", tx[0]["match"])
        self.assertEqual(queries.employer_debarments(self.con, self.acme_ca, path=self.csv, today=TODAY), [])

    def test_name_only_entries_match_a_dba_part(self):
        hit = queries.employer_debarments(self.con, self.analytics, path=self.csv, today=TODAY)
        self.assertEqual([(d["program"], d["status"]) for d in hit], [("H-1B", "ended")])
        self.assertIn("no address", hit[0]["match"])

    def test_full_list_with_matched_employers(self):
        rows = queries.debarments(self.con, path=self.csv, today=TODAY)
        self.assertEqual([len(r["employers"]) for r in rows][1:], [1, 0])
        self.assertTrue(all(e["state"] == "TX" for e in rows[0]["employers"]))
        self.assertEqual(rows[2]["status"], "active")  # permanent
        self.assertNotIn("keys", rows[0])

    def test_parser_helpers(self):
        self.assertEqual(parse_debarments.iso_date("July,10, 2030"), "2030-07-10")
        self.assertEqual(parse_debarments.iso_date("August 30. 2027"), "2027-08-30")
        self.assertEqual(parse_debarments.iso_date("5/12/2025"), "2025-05-12")
        self.assertEqual(parse_debarments.iso_date("Permanent"), "permanent")
        self.assertEqual(parse_debarments.state_of("Shelter Island, New\nYork"), "NY")
        self.assertEqual(parse_debarments.state_of("Auburn Hills, MI"), "MI")
        self.assertEqual(parse_debarments.state_of("Georgia"), "GA")
        self.assertEqual(parse_debarments.state_of(""), "")


if __name__ == "__main__":
    unittest.main()
