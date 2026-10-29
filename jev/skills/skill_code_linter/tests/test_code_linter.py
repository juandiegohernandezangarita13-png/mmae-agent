"""
Pruebas unitarias para skill_code_linter.
"""
import unittest
from jev.skills.skill_code_linter.handler import handle, lint_python_code


class TestSkillCodeLinter(unittest.TestCase):

    def test_01_valid_code(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        res = lint_python_code(code)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["stats"]["functions"], 1)

    def test_02_syntax_error(self):
        bad_code = "def broken(\n    return 42"
        res = lint_python_code(bad_code)
        self.assertFalse(res["valid"])
        self.assertEqual(res["errors"][0]["type"], "SyntaxError")

    def test_03_placeholder_detection(self):
        code_with_pass = "def unfinished():\n    pass\n"
        res = lint_python_code(code_with_pass, strict_placeholders=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any(e["type"] == "empty_placeholder" for e in res["errors"]))

    def test_04_todo_comment_warning(self):
        code_with_todo = "x = 10\n# TODO: optimizar algoritmo\n"
        res = lint_python_code(code_with_todo)
        self.assertTrue(res["valid"])
        self.assertTrue(any(w["type"] == "todo_marker" for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()
