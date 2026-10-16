"""Tests for the red flags on an employer's own applications, on the small made-up database.

Run from the repo root:  python3 -m unittest discover dashboard/tests
"""
import os, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import queries  # noqa: E402
from test_queries import make_db  # noqa: E402


def loosened(min_n=1):
    """The real flags with the minimum application count lowered, so the tiny test employers can trip them."""
    return [(*f[:6], min_n, f[7]) for f in queries.RED_FLAGS]


class RedFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = queries.connect(make_db(tempfile.mkdtemp()))
        hits = queries.search_employers(cls.con, "acme software")
        cls.acme_tx = next(h["employer_id"] for h in hits if h["state"] == "TX" and h["program"] == "H-1B")
        cls.acme_h2b = next(h["employer_id"] for h in hits if h["program"] == "H-2B")

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_minimum_applications_keep_small_filers_unflagged(self):
        self.assertEqual(queries.red_flags(self.con, self.acme_tx), [])

    def test_withdrawn_share_trips_with_counts_and_baseline(self):
        # Acme TX filed two applications; one was withdrawn (50%, above the 40% line).
        with mock.patch.object(queries, "RED_FLAGS", loosened()):
            queries._flag_baselines.cache_clear()
            flags = {f["key"]: f for f in queries.red_flags(self.con, self.acme_tx)}
        self.assertEqual((flags["not_certified"]["applications"], flags["not_certified"]["of"]), (1, 2))
        self.assertIsNotNone(flags["not_certified"]["baseline"])
        self.assertIn("1 of 2 applications (50%)", flags["not_certified"]["detail"])
        # Both offers are 4% or more above the prevailing wage, so the floor flag stays off.
        self.assertNotIn("wage_floor", flags)
        queries._flag_baselines.cache_clear()

    def test_flags_apply_only_to_their_programs(self):
        with mock.patch.object(queries, "RED_FLAGS", loosened()):
            queries._flag_baselines.cache_clear()
            keys = {f["key"] for f in queries.red_flags(self.con, self.acme_h2b)}
        self.assertFalse(keys & {"wage_floor", "entry_level", "not_certified"})
        queries._flag_baselines.cache_clear()


if __name__ == "__main__":
    unittest.main()
