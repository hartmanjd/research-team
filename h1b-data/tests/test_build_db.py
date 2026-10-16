"""Tests for the SQLite database builder and the workbook converter.

Run from the repo root:  python3 -m unittest discover h1b-data/tests
"""
import csv, io, json, os, sqlite3, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import build_db, build_filers, fetch_whd, provenance, xlsx_to_csv  # noqa: E402


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def filing(case, name, state, zip_, fein, dba="", visa="H-1B", status="Certified"):
    return {"CASE_NUMBER": case, "CASE_STATUS": status, "VISA_CLASS": visa, "EMPLOYER_NAME": name,
            "TRADE_NAME_DBA": dba, "EMPLOYER_ADDRESS1": "1 Main St", "EMPLOYER_CITY": "Town",
            "EMPLOYER_STATE": state, "EMPLOYER_POSTAL_CODE": zip_, "EMPLOYER_FEIN": fein,
            "NAICS_CODE": "1111", "H-1B_DEPENDENT": "No", "WILLFUL_VIOLATOR": "No",
            **({"BASIC_WAGE_RATE_FROM": "18.25"} if visa == "H-2B" else
               {"TOTAL_WORKER_POSITIONS": "2", "WAGE_RATE_OF_PAY_FROM": "$95,000.50"})}


def whd_case(case_id, trade, legal, state, zip_, h1b=0, h2b=0):
    row = {f: "" for f in fetch_whd.FIELDS}
    row.update({"case_id": str(case_id), "trade_nm": trade, "legal_name": legal, "st_cd": state,
                "zip_cd": zip_, "h1b_violtn_cnt": str(h1b), "h2b_violtn_cnt": str(h2b),
                "bw_atp_amt": "1500.5", "load_dt": "2024-01-02T03:04:05"})
    return row


class BuildDbTests(unittest.TestCase):
    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        p = lambda n: os.path.join(d, n)
        write_csv(p("lca.csv"), [
            filing("I-1", "Acme Software LLC", "TX", "78701", "111111111"),
            filing("I-2", "ACME SOFTWARE, INC.", "TX", "78701", "111111111"),
            filing("I-3", "Delta Labs", "CA", "94105", "333333333", dba="Delta Research"),
        ])
        write_csv(p("h2b.csv"), [
            filing("H-1", "Beta Farms", "FL", "33101", "222222222", visa="H-2B"),
            filing("H-2", "Acme Software", "NY", "10001", "999999999", visa="H-2B"),
        ])
        with mock.patch("sys.stdout", io.StringIO()):
            build_filers.main([p("filers_lca.csv"), p("lca.csv")])
            build_filers.main([p("filers_h2b.csv"), p("h2b.csv")])
        write_csv(p("whd.csv"), [
            whd_case(10, "Acme Software", "Acme Software LLC", "TX", "78701", h1b=2),  # ZIP match
            whd_case(11, "", "Beta Farms Inc", "FL", "33999", h2b=1),                 # state match only
            whd_case(12, "Delta Research", "", "CA", "94105"),                       # matches the DBA
            whd_case(13, "Gamma Co", "Gamma Co", "WA", "98101"),                     # no match
        ], fields=fetch_whd.FIELDS)
        provenance.write_manifest(p("whd.csv"), fetch_whd.__file__,
                                  sources=[{"url": fetch_whd.URL}])
        write_csv(p("bench.csv"), [{"rule": "clean name + ZIP", "false_match_rate": "0.04"},
                                   {"rule": "clean name + state", "false_match_rate": "0.03"}])
        provenance.write_manifest(p("bench.csv"), provenance.__file__)
        self.db = p("research.db")
        self.args = [self.db, "--lca", p("filers_lca.csv"), "--h2b", p("filers_h2b.csv"),
                     "--whd", p("whd.csv"), "--benchmark", p("bench.csv")]
        with mock.patch("sys.stdout", io.StringIO()):
            build_db.main(self.args)
        self.con = sqlite3.connect(self.db)
        self.addCleanup(self.con.close)

    def q(self, sql, *args):
        return self.con.execute(sql, args).fetchall()

    def test_every_application_links_to_its_employer(self):
        rows = self.q("SELECT a.case_number, e.program, e.name_clean, e.state FROM applications a"
                      " JOIN employers e USING (employer_id) ORDER BY a.case_number")
        self.assertEqual(rows, [("H-1", "H-2B", "BETA FARMS", "FL"), ("H-2", "H-2B", "ACME SOFTWARE", "NY"),
                                ("I-1", "H-1B", "ACME SOFTWARE", "TX"), ("I-2", "H-1B", "ACME SOFTWARE", "TX"),
                                ("I-3", "H-1B", "DELTA LABS", "CA")])
        self.assertEqual(self.q("SELECT n_applications FROM employers WHERE name_clean='ACME SOFTWARE'"
                                " AND program='H-1B'"), [(2,)])

    def test_matches_use_the_strongest_rule_and_carry_its_error_rate(self):
        rows = self.q("SELECT m.case_id, e.name_clean, e.program, m.method, m.est_false_match_rate,"
                      " m.whd_name_field, m.employer_name_field FROM matches m"
                      " JOIN employers e USING (employer_id) ORDER BY m.case_id, m.whd_name_field")
        self.assertEqual(rows, [
            (10, "ACME SOFTWARE", "H-1B", "clean name + ZIP", 0.04, "trade name", "name"),  # both names match; trade name is tried first
            (11, "BETA FARMS", "H-2B", "clean name + state", 0.03, "legal name", "name"),
            (12, "DELTA LABS", "H-1B", "clean name + ZIP", 0.04, "trade name", "DBA"),
        ])
        # Same cleaned name in another state (Acme in NY) is not linked to case 10.
        self.assertEqual(self.q("SELECT COUNT(*) FROM matches WHERE case_id=10"), [(1,)])

    def test_applications_keep_disclosure_columns_and_numbers(self):
        rows = self.q("SELECT case_number, naics_code, total_worker_positions, wage_rate_of_pay_from"
                      " FROM applications WHERE case_number IN ('I-1', 'H-1') ORDER BY case_number")
        self.assertEqual(rows, [("H-1", "1111", None, None), ("I-1", "1111", 2, 95000.5)])
        self.assertEqual(self.q("SELECT basic_wage_rate_from FROM applications WHERE case_number='H-1'"), [(18.25,)])

    def test_cases_keep_numbers_and_load_dates(self):
        self.assertEqual(self.q("SELECT case_id, h1b_violtn_cnt, bw_atp_amt, load_dt FROM violation_cases"
                                " WHERE case_id=10"), [(10, 2, 1500.5, "2024-01-02T03:04:05")])
        self.assertEqual(self.q("SELECT COUNT(*) FROM violation_cases"), [(4,)])

    def test_every_row_points_to_a_recorded_source(self):
        for table in ["employers", "applications", "violation_cases"]:
            orphans = self.q(f"SELECT COUNT(*) FROM {table} t LEFT JOIN sources s USING (source_id)"
                             " WHERE s.sha256 IS NULL")
            self.assertEqual(orphans, [(0,)], table)
        files = [r[0] for r in self.q("SELECT file FROM sources ORDER BY source_id")]
        self.assertEqual(files, ["filers_lca.csv", "filers_lca_applications.csv", "filers_h2b.csv",
                                 "filers_h2b_applications.csv", "whd.csv", "bench.csv"])
        whd_src = self.q("SELECT urls, rows FROM sources WHERE file='whd.csv'")
        self.assertEqual(whd_src, [(fetch_whd.URL, 4)])

    def test_database_has_its_own_manifest(self):
        m = provenance.verify_manifest(self.db)
        self.assertIsNone(m["rows"])
        self.assertEqual(m["params"]["tables"]["matches"], 3)
        self.assertEqual(len(m["inputs"]), 6)

    def test_refuses_an_input_changed_after_its_manifest(self):
        with open(os.path.join(self.d, "whd.csv"), "a") as f:
            f.write("tampered\n")
        with self.assertRaisesRegex(ValueError, "whd.csv has changed"):
            build_db.main(self.args)


class XlsxToCsvTests(unittest.TestCase):
    def test_converts_first_sheet_and_skips_blank_rows(self):
        from openpyxl import Workbook
        import datetime
        d = tempfile.mkdtemp()
        wb = Workbook()
        ws = wb.active
        ws.append(["CASE_NUMBER", "EMPLOYER_POSTAL_CODE", "RECEIVED_DATE", "WAGE"])
        ws.append(["I-1", "02134", datetime.datetime(2025, 1, 31), 50000.0])
        ws.append([None, None, None, None])
        ws.append(["I-2", None, None, 12.5])
        xlsx = os.path.join(d, "in.xlsx")
        wb.save(xlsx)
        out = os.path.join(d, "out.csv")
        with mock.patch("sys.stdout", io.StringIO()):
            xlsx_to_csv.main([xlsx, out, "--source-url", "https://example.gov/in.xlsx"])
        with open(out, newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows, [["CASE_NUMBER", "EMPLOYER_POSTAL_CODE", "RECEIVED_DATE", "WAGE"],
                                ["I-1", "02134", "2025-01-31", "50000"], ["I-2", "", "", "12.5"]])
        m = provenance.verify_manifest(out)
        self.assertEqual((m["rows"], m["inputs"][0]["file"], m["inputs"][0]["rows"]), (2, "in.xlsx", None))
        self.assertEqual(m["sources"], [{"url": "https://example.gov/in.xlsx"}])


if __name__ == "__main__":
    unittest.main()
