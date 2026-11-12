"""Synthetic regressions for independently audited candidate transformations.

Only in-memory fixtures are used; no benchmark inputs or grading results.
"""
import sqlite3
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "v2"))
from ranking import quality_features
from semantic_repairs import candidates


def projection_candidate(sql, headings):
    proposals = candidates(sql, "", {}, {"columns": headings}, None)
    return next(sql for sql, reason, _ in proposals
                if reason == "compositional_projection")


class ExperimentAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE person (name TEXT, age INTEGER);
            INSERT INTO person VALUES ('Alice', 30), ('Bob', 10), ('Bob', 20);
        """)

    def test_removed_projection_keeps_ordinal_order_expression(self):
        original = ("SELECT name, COUNT(*) AS n FROM person "
                    "GROUP BY name ORDER BY 2 DESC LIMIT 1")
        proposed = projection_candidate(original, ["name"])
        expected = [(row[0],) for row in self.db.execute(original)]
        self.assertEqual(list(self.db.execute(proposed)), expected)

    def test_reordered_projection_keeps_ordinal_order_expression(self):
        original = "SELECT name, age FROM person ORDER BY 1, age"
        proposed = projection_candidate(original, ["age", "name"])
        expected = [(row[1], row[0]) for row in self.db.execute(original)]
        self.assertEqual(list(self.db.execute(proposed)), expected)

    def test_reordered_projection_keeps_ordinal_group_expression(self):
        original = "SELECT name, COUNT(*) FROM person GROUP BY 1 ORDER BY name"
        proposed = projection_candidate(original, ["count(*)", "name"])
        expected = [(row[1], row[0]) for row in self.db.execute(original)]
        self.assertEqual(list(self.db.execute(proposed)), expected)

    def test_window_aggregate_does_not_require_grouping(self):
        sql = "SELECT name, SUM(age) OVER () FROM person"
        self.assertEqual(len(list(self.db.execute(sql))), 3)
        self.assertNotIn("ungrouped_mixed_projection", quality_features(sql, "", {}))

    def test_filtered_window_aggregate_does_not_require_grouping(self):
        sql = "SELECT name, SUM(age) FILTER (WHERE age > 15) OVER () FROM person"
        self.assertEqual(len(list(self.db.execute(sql))), 3)
        self.assertNotIn("ungrouped_mixed_projection", quality_features(sql, "", {}))

    def test_window_over_regular_aggregate_keeps_grouping_feature(self):
        sql = "SELECT name, SUM(SUM(age)) OVER () FROM person"
        self.assertEqual(len(list(self.db.execute(sql))), 1)
        self.assertLess(quality_features(sql, "", {})["ungrouped_mixed_projection"], 0)

    def test_regular_aggregate_still_gets_grouping_feature(self):
        features = quality_features("SELECT name, SUM(age) FROM person", "", {})
        self.assertLess(features["ungrouped_mixed_projection"], 0)


if __name__ == "__main__":
    unittest.main()
