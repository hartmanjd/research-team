"""Tests for the summary tables the database build stores for the website, on the small made-up database.

Run from the repo root:  python3 -m unittest discover dashboard/tests
"""
import os, shutil, sqlite3, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import queries  # noqa: E402
from test_queries import make_db  # noqa: E402


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        cls.built = make_db(d)
        cls.bare = os.path.join(d, "bare.db")  # the same database without the summary tables
        shutil.copy(cls.built, cls.bare)
        con = sqlite3.connect(cls.bare)
        con.execute("DROP TABLE flag_baselines")
        con.execute("DROP TABLE rep_filings")
        con.commit()
        con.close()

    def tearDown(self):
        for fn in (queries._flag_baselines, queries._rep_index):
            fn.cache_clear()

    def test_build_stores_the_summaries(self):
        con = queries.connect(self.built)
        try:
            self.assertTrue(queries._has_table(con, "flag_baselines"))
            self.assertTrue(queries._has_table(con, "rep_filings"))
            self.assertEqual(con.execute("SELECT SUM(applications) FROM rep_filings").fetchone()[0],
                             con.execute("SELECT COUNT(*) FROM applications").fetchone()[0])
        finally:
            con.close()

    def test_stored_and_computed_values_agree(self):
        self.assertEqual(queries._flag_baselines(self.built), queries._flag_baselines(self.bare))
        self.assertEqual(queries._rep_index(self.built), queries._rep_index(self.bare))
        self.assertTrue(queries._rep_index(self.built)["reps"]["firm"])

    def test_add_summaries_rewrites_the_tables(self):
        path = os.path.join(tempfile.mkdtemp(), "again.db")
        shutil.copy(self.built, path)
        con = sqlite3.connect(path)
        queries.add_summaries(con)
        queries.add_summaries(con)
        n = con.execute("SELECT COUNT(*) FROM flag_baselines").fetchone()[0]
        con.close()
        self.assertEqual(n, sum(len(f[2]) for f in queries.RED_FLAGS))
        self.assertEqual(queries._flag_baselines(path), queries._flag_baselines(self.bare))


if __name__ == "__main__":
    unittest.main()
