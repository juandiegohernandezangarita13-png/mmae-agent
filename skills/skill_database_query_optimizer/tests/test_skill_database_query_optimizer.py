"""
Tests unitarios para skill_database_query_optimizer.
"""
import unittest
import handler

class TestSqlOptimizer(unittest.TestCase):
    def test_detects_select_star_and_no_limit(self):
        query = "SELECT * FROM orders WHERE status = 'pending'"
        res = handler.handle(query=query)
        self.assertEqual(res.get("status"), "success")
        self.assertFalse(res.get("is_production_ready"))
        self.assertGreater(len(res.get("recommendations")), 0)

    def test_clean_query_high_score(self):
        query = "SELECT id, total FROM orders WHERE id = 42 LIMIT 1;"
        res = handler.handle(query=query)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("health_score"), 100)

if __name__ == "__main__":
    unittest.main()
