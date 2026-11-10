"""Focused behavioral tests of generic, feedback-driven SQL hypotheses."""
import unittest

from repairs import candidates


class RepairTests(unittest.TestCase):
    def test_duplicate_feedback_proposes_distinct(self):
        result = candidates("SELECT name FROM person", "List people names",
                            {"ok": True, "row_count": 5},
                            {"columns": ["name"], "row_count": 3})
        self.assertIn("SELECT DISTINCT name FROM person", [row[0] for row in result])

    def test_public_headers_reorder_and_remove_columns(self):
        result = candidates("SELECT age, name, id FROM person", "Show names and ages",
                            {"ok": True}, {"columns": ["name", "age"]})
        self.assertIn("SELECT name, age FROM person", [row[0] for row in result])

    def test_no_result_value_synthesis(self):
        result = candidates("SELECT name FROM person", "What names?", {"ok": True},
                            {"columns": ["name"], "rows": [["secret-canary"]]})
        self.assertTrue(all("secret-canary" not in sql for sql, _, _ in result))

    def test_non_readonly_input_rejected(self):
        self.assertEqual([], candidates("DELETE FROM person", "delete", {}, {}))
        self.assertEqual([], candidates("SELECT name FROM person; DROP TABLE person", "", {}, {}))

    def test_malicious_heading_not_executed(self):
        result = candidates("SELECT name FROM person", "", {},
                            {"columns": ["(SELECT load_extension('evil'))"]})
        self.assertTrue(all("evil" not in sql for sql, _, _ in result))

    def test_schema_missing_join_and_qualification(self):
        schema = [
            {"name": "purchase", "columns": [{"name": "member_id"}],
             "foreign_keys": [{"from": "member_id", "table": "member", "to": "id"}]},
            {"name": "member", "columns": [{"name": "id"}, {"name": "level"}],
             "foreign_keys": []}]
        result = candidates("SELECT COUNT(*) FROM purchase WHERE level = 6", "Count purchases",
                            {"error": {"message": "no such column: level"}}, {}, schema)
        self.assertTrue(any("JOIN member ON purchase.member_id = member.id" in sql
                            and "member.level = 6" in sql for sql, _, _ in result))

    def test_aggregate_filter_moved_to_having(self):
        result = candidates("SELECT name FROM person WHERE COUNT(*) > 2", "Names appearing often",
                            {"error": {"message": "misuse of aggregate"}}, {})
        self.assertTrue(any("GROUP BY name HAVING COUNT(*) > 2" in sql
                            for sql, _, _ in result))

    def test_nested_aggregate_filter_keeps_scope(self):
        result = candidates("SELECT name FROM person WHERE age > (SELECT AVG(age) FROM person)",
                            "Names above average age", {}, {})
        self.assertFalse(any(reason == "aggregate_filter_to_having"
                             for _, reason, _ in result))

    def test_nested_aggregate_order_keeps_scope(self):
        result = candidates("SELECT name FROM person ORDER BY (SELECT AVG(age) FROM person)",
                            "Show names", {}, {})
        self.assertFalse(any(reason == "group_for_aggregate_order"
                             for _, reason, _ in result))

    def test_row_filters_stay_before_aggregation(self):
        result = candidates("SELECT name FROM person WHERE age > 20 AND COUNT(*) > 2",
                            "Repeated names of adults", {}, {})
        repaired = [sql for sql, reason, _ in result if reason == "aggregate_filter_to_having"]
        self.assertEqual(["SELECT name FROM person WHERE age > 20 GROUP BY name HAVING COUNT(*) > 2"],
                         repaired)

    def test_mixed_or_filter_is_not_moved(self):
        result = candidates("SELECT name FROM person WHERE age > 20 OR COUNT(*) > 2", "", {}, {})
        self.assertFalse(any(reason == "aggregate_filter_to_having"
                             for _, reason, _ in result))

    def test_equal_count_nodes_are_independently_repaired(self):
        result = candidates("SELECT COUNT(id) FROM person HAVING COUNT(id) > 2", "", {}, {})
        repaired = [sql for sql, reason, _ in result if reason == "count_distinct"]
        self.assertIn("SELECT COUNT(DISTINCT id) FROM person HAVING COUNT(id) > 2", repaired)
        self.assertIn("SELECT COUNT(id) FROM person HAVING COUNT(DISTINCT id) > 2", repaired)

    def test_order_direction_uses_sqlite_null_default(self):
        result = candidates("SELECT name FROM person ORDER BY name DESC", "Sort alphabetically", {}, {})
        repaired = [sql for sql, reason, _ in result if reason == "question_order_direction"]
        self.assertEqual(["SELECT name FROM person ORDER BY name ASC"], repaired)

    def test_question_limit_not_example_count(self):
        result = candidates("SELECT name FROM person ORDER BY age DESC", "Top 3 oldest people",
                            {"ok": True, "row_count": 20}, {"row_count": 1})
        self.assertTrue(any("LIMIT 3" in sql for sql, _, _ in result))
        self.assertFalse(any("LIMIT 1" in sql for sql, _, _ in result))


if __name__ == "__main__":
    unittest.main()
