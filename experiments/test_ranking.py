"""Synthetic tests for the optional untrained candidate quality prior."""
import unittest
from ranking import quality, quality_features


class RankingTests(unittest.TestCase):
    def test_projection_shape(self):
        example = {"columns": ["name"]}
        self.assertGreater(quality("SELECT name FROM person", "", example),
                           quality("SELECT name, age FROM person", "", example))

    def test_aggregate_alignment(self):
        example = {"columns": ["client_id", "sum(amount)"]}
        good = "SELECT client_id, SUM(amount) FROM payment GROUP BY client_id"
        bad = "SELECT client_id, amount FROM payment"
        self.assertGreater(quality(good, "Maximum total amount", example),
                           quality(bad, "Maximum total amount", example))

    def test_qualifiers_do_not_change_projection_alignment(self):
        example = {"columns": ["avg(T1.age)"]}
        self.assertEqual(quality_features("SELECT AVG(p.age) FROM person p", "", example)["projection_alignment"], 1.5)

    def test_join_tautology(self):
        good = "SELECT p.name FROM person p JOIN event e ON p.id = e.person_id"
        bad = "SELECT p.name FROM person p JOIN event e ON p.id = p.id"
        self.assertGreater(quality(good, "", {"columns": ["name"]}),
                           quality(bad, "", {"columns": ["name"]}))

    def test_frequency_order_resolves_alias(self):
        sql = "SELECT kind, COUNT(*) AS n FROM event GROUP BY kind ORDER BY n DESC LIMIT 1"
        self.assertNotIn("frequency_order", quality_features(sql, "Most common kind", {"columns": ["kind"]}))

    def test_schema_spelling_prior(self):
        schema = [{"name": "person", "columns": [{"name": "name"}]}]
        self.assertGreater(quality("SELECT name FROM person", "", {}, schema),
                           quality("SELECT nmae FROM person", "", {}, schema))

    def test_cte_is_not_missing_schema_table(self):
        schema = [{"name": "person", "columns": [{"name": "name"}]}]
        features = quality_features("WITH names AS (SELECT name FROM person) SELECT name FROM names", "", {}, schema)
        self.assertEqual(features["schema_missing_tables"], 0)

    def test_no_row_value_dependence(self):
        sql = "SELECT name FROM person"
        self.assertEqual(quality(sql, "", {"columns": ["name"], "rows": [["Alice"]]}),
                         quality(sql, "", {"columns": ["name"], "rows": [["Bob"]]}))

    def test_never_requires_anti_condition(self):
        good = "SELECT name FROM person WHERE id NOT IN (SELECT person_id FROM event)"
        bad = "SELECT name FROM person JOIN event ON person.id = event.person_id WHERE event.kind <> 'visit'"
        self.assertNotIn("missing_anti_condition", quality_features(good, "People who never visited", {}))
        self.assertIn("missing_anti_condition", quality_features(bad, "People who never visited", {}))

    def test_mutating_sql_invalid(self):
        self.assertEqual(quality("DROP TABLE person", "", {}), -1000.0)

    def test_any_does_not_mean_after_maximum(self):
        max_sql = "SELECT name FROM item WHERE stamp > (SELECT MAX(stamp) FROM event)"
        min_sql = "SELECT name FROM item WHERE stamp > (SELECT MIN(stamp) FROM event)"
        self.assertGreater(quality(min_sql, "Items after any event", {}),
                           quality(max_sql, "Items after any event", {}))


if __name__ == "__main__":
    unittest.main()
