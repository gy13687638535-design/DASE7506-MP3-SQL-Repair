"""Synthetic tests for proposed compositional repair rules."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'v2'))
from semantic_repairs import candidates


def proposals(sql, question='', example=None, schema=None):
    return candidates(sql, question, {}, example or {}, schema)


class SemanticTests(unittest.TestCase):
    def test_removed_projection_alias_is_expanded_in_order(self):
        result = proposals('SELECT name, COUNT(*) AS n FROM person GROUP BY name ORDER BY n DESC LIMIT 3',
                           'Top three names', {'columns': ['name']})
        self.assertIn('SELECT name FROM person GROUP BY name ORDER BY COUNT(*) DESC LIMIT 3',
                      [x[0] for x in result])

    def test_introduced_sum_repairs_grouping_and_order(self):
        result = proposals('SELECT c.id, p.amount FROM customer c JOIN payment p ON c.id = p.customer_id ORDER BY p.amount DESC LIMIT 1',
                           'Highest total amount per customer', {'columns': ['id', 'sum(amount)']})
        self.assertTrue(any('SUM(p.amount)' in sql and 'GROUP BY c.id' in sql
                            and 'ORDER BY SUM(p.amount) DESC' in sql for sql, _, _ in result))

    def test_pruning_keeps_filtered_tables(self):
        result = proposals("SELECT a.name FROM person a JOIN visit b ON a.id = b.person_id WHERE b.kind = 'work'")
        self.assertFalse(any(reason.startswith('prune') for _, reason, _ in result))

    def test_unused_join_can_be_pruned(self):
        result = proposals('SELECT SUM(a.value) FROM inventory a JOIN link b ON a.id = b.id',
                           'Total inventory value')
        self.assertIn('SELECT SUM(a.value) FROM inventory AS a', [x[0] for x in result])

    def test_negative_membership_uses_correlated_exists(self):
        result = proposals("SELECT DISTINCT p.name FROM person p JOIN visit v ON p.id = v.person_id WHERE v.kind <> 'work'",
                           'People who never made work visits')
        sql = next(sql for sql, reason, _ in result if reason == 'negative_membership_not_exists')
        self.assertIn("NOT EXISTS(SELECT 1 FROM visit AS v WHERE p.id = v.person_id AND v.kind = 'work')", sql)
        self.assertNotIn('JOIN', sql)

    def test_numeric_literal_requires_question_and_numeric_field(self):
        result = proposals("SELECT * FROM item WHERE duration = '4'", 'Items lasting 4 minutes')
        self.assertTrue(any("CAST(duration AS REAL) = 4" in sql for sql, _, _ in result))
        self.assertFalse(proposals("SELECT * FROM item WHERE postal_code = '004'", 'Postal code 004'))

    def test_after_any_changes_max_to_min(self):
        result = proposals('SELECT id FROM event WHERE day > (SELECT MAX(day) FROM archive)', 'Events after any archived event')
        self.assertTrue(any('SELECT MIN(day)' in sql for sql, _, _ in result))

    def test_quoted_result_value_never_copied(self):
        result = proposals('SELECT name FROM person', 'Names', {'columns': ['name'], 'rows': [['private-value']]})
        self.assertTrue(all('private-value' not in sql for sql, _, _ in result))

    def test_mutation_and_stacked_queries_rejected(self):
        self.assertEqual([], proposals('DROP TABLE person'))
        self.assertEqual([], proposals('SELECT * FROM person; DELETE FROM person'))

    def test_malicious_heading_is_rejected(self):
        result = proposals('SELECT name FROM person', '', {'columns': ["(SELECT load_extension('evil'))"]})
        self.assertTrue(all('evil' not in sql for sql, _, _ in result))


if __name__ == '__main__':
    unittest.main()
