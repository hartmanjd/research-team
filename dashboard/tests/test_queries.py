"""Tests for the dashboard's lookups, on a small made-up database.

Run from the repo root:  python3 -m unittest discover dashboard/tests
"""
import io, os, sqlite3, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "h1b-data", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "h1b-data", "tests"))
import build_db, build_filers, fetch_whd, provenance, queries  # noqa: E402
from test_build_db import filing, whd_case, write_csv  # noqa: E402

LCA_URL = "https://example.gov/lca.xlsx"


def make_db(d):
    p = lambda n: os.path.join(d, n)
    write_csv(p("lca.csv"), [
        filing("I-1", "Acme Software LLC", "TX", "78701", "111111111"),
        filing("I-2", "ACME SOFTWARE, INC.", "TX", "78701", "111111111", status="Withdrawn"),
        filing("I-3", "Acme Software", "CA", "94105", "111111111"),
        filing("I-4", "Acme Analytics", "NY", "10001", "444444444"),
    ])
    write_csv(p("h2b.csv"), [filing("H-1", "Acme Software", "TX", "78701", "111111111", visa="H-2B")])
    with mock.patch("sys.stdout", io.StringIO()):
        build_filers.main([p("filers_lca.csv"), p("lca.csv"), "--source-url", LCA_URL])
        build_filers.main([p("filers_h2b.csv"), p("h2b.csv")])
    old = whd_case(10, "Acme Software", "", "TX", "78701", h1b=2)
    old.update(findings_end_date="2019-05-01", bw_atp_amt="1000", cmp_assd="250")
    new = whd_case(11, "", "Acme Software LLC", "TX", "73301")  # same state, other ZIP
    new.update(findings_end_date="2023-02-01", bw_atp_amt="500", cmp_assd="0")
    write_csv(p("whd.csv"), [old, new, whd_case(12, "Zeta", "Zeta", "WA", "98101")],
              fields=fetch_whd.FIELDS)
    provenance.write_manifest(p("whd.csv"), fetch_whd.__file__, sources=[{"url": fetch_whd.URL}])
    write_csv(p("bench.csv"), [{"rule": "clean name + ZIP", "false_match_rate": "0.04"},
                               {"rule": "clean name + state", "false_match_rate": "0.03"}])
    provenance.write_manifest(p("bench.csv"), provenance.__file__)
    with mock.patch("sys.stdout", io.StringIO()):
        build_db.main([p("research.db"), "--lca", p("filers_lca.csv"), "--h2b", p("filers_h2b.csv"),
                       "--whd", p("whd.csv"), "--benchmark", p("bench.csv")])
    return p("research.db")


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.con = queries.connect(make_db(cls.d))

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def acme_tx(self, program="H-1B"):
        return next(h for h in queries.search_employers(self.con, "acme software")
                    if h["state"] == "TX" and h["program"] == program)

    def test_search_cleans_the_text_and_ranks_exact_names_first(self):
        hits = queries.search_employers(self.con, "  Acme Software, Inc. ")
        self.assertEqual([(h["employer_name"], h["state"], h["program"]) for h in hits][:3],
                         [("Acme Software LLC", "TX", "H-1B"), ("Acme Software", "CA", "H-1B"),
                          ("Acme Software", "TX", "H-2B")])
        self.assertIn("Acme Analytics", [h["employer_name"] for h in queries.search_employers(self.con, "acme")])
        self.assertEqual(queries.search_employers(self.con, "llc"), [])  # only legal-form words

    def test_summary_totals_the_linked_cases(self):
        s = queries.summary(self.con, self.acme_tx()["employer_id"])
        self.assertEqual((s["applications"], s["certified"], s["cases"]), (2, 1, 2))
        self.assertEqual((s["back_wages"], s["penalties"], s["h1b_violations"]), (1500.0, 250.0, 2))

    def test_cases_are_newest_first_and_say_how_they_were_linked(self):
        cs = queries.cases(self.con, self.acme_tx()["employer_id"])
        self.assertEqual([(c["case_id"], c["method"]) for c in cs],
                         [(11, "clean name + state"), (10, "clean name + ZIP")])
        self.assertEqual(cs[0]["source_urls"], fetch_whd.URL)
        self.assertEqual(cs[0]["load_dt"], "2024-01-02T03:04:05")
        self.assertEqual(queries.match_label(cs[0]["method"], cs[0]["est_false_match_rate"]),
                         "Matched by clean name + state; about 3% of links made this way were wrong "
                         "in the tax-ID test")

    def test_applications_link_back_to_the_dol_file(self):
        apps = queries.applications(self.con, self.acme_tx()["employer_id"])
        self.assertEqual([(a["case_number"], a["case_status"]) for a in apps],
                         [("I-1", "Certified"), ("I-2", "Withdrawn")])
        self.assertEqual({a["dol_file_url"] for a in apps}, {LCA_URL})  # lca.csv came from lca.xlsx
        self.assertEqual(queries.dol_file_url("LCA_Q1.csv", "https://x.gov/LCA_Q2.xlsx;https://x.gov/LCA_Q1.xlsx"),
                         "https://x.gov/LCA_Q1.xlsx")
        self.assertEqual(len(queries.applications(self.con, self.acme_tx()["employer_id"], limit=1)), 1)

    def test_same_tax_id_finds_other_programs_and_addresses(self):
        rel = queries.same_tax_id(self.con, self.acme_tx()["employer_id"])
        self.assertEqual([(r["program"], r["state"]) for r in rel], [("H-1B", "CA"), ("H-2B", "TX")])

    def test_employer_row_carries_its_source(self):
        e = queries.employer(self.con, self.acme_tx()["employer_id"])
        self.assertEqual((e["source_file"], e["source_urls"]), ("filers_lca.csv", LCA_URL))
        self.assertIsNone(queries.employer(self.con, 999999))

    def test_database_is_opened_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.con.execute("DELETE FROM employers")

    def test_missing_database_gives_a_clear_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "build_db.py"):
            queries.connect(os.path.join(self.d, "nope.db"))


if __name__ == "__main__":
    unittest.main()
