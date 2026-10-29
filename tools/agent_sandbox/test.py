"""
Pruebas unitarias para el Sandbox de ejecución del Agente (AgentSandboxRunner).
"""
import unittest
from pathlib import Path

from sandbox_runner import AgentSandboxRunner


class TestAgentSandbox(unittest.TestCase):
    def setUp(self):
        self.runner = AgentSandboxRunner()

    def test_run_safe_command(self):
        res = self.runner.run_command("Write-Output 'ACE Sandbox OK'", timeout=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("ACE Sandbox OK", res["stdout"])
        self.assertFalse(res["blocked"])

    def test_block_dangerous_command(self):
        res = self.runner.run_command("format c: /q", timeout=10)
        self.assertFalse(res["success"])
        self.assertTrue(res["blocked"])
        self.assertIn("bloqueado por seguridad", res["stderr"])

    def test_run_python_code(self):
        code = """
import math
print(f"PI: {round(math.pi, 4)}")
"""
        res = self.runner.run_python_code(code, timeout=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("PI: 3.1416", res["stdout"])

    def test_timeout_enforcement(self):
        code = """
import time
time.sleep(5)
print("Finished")
"""
        res = self.runner.run_python_code(code, timeout=1)
        self.assertFalse(res["success"])
        self.assertIn("Timeout", res["stderr"])


if __name__ == "__main__":
    unittest.main()
