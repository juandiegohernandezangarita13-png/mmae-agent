"""
Pruebas unitarias para las herramientas de smolvm (SmolvmRunnerTool y SmolfileGeneratorTool).
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from jev.tools.smolvm_runner import SmolvmRunnerTool, SmolfileGeneratorTool


class TestSmolvmTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.runner = SmolvmRunnerTool(workspace_dir=self.temp_dir)
        self.generator = SmolfileGeneratorTool(workspace_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_smolvm_info_action(self):
        result = self.runner.execute(action="info")
        self.assertTrue(result.success)
        self.assertIn("ESTADO DE SMOLVM", result.output)
        self.assertIn("hypervisor_requirement", result.data)
        self.assertIn("microvm_startup_time", result.data)

    def test_smolvm_run_fallback_safe_command(self):
        result = self.runner.execute(
            action="run",
            command="echo 'smolvm isolated test'",
            image="alpine"
        )
        self.assertTrue(result.success)
        self.assertIn("smolvm isolated test", result.output)

    def test_smolvm_blocked_dangerous_command(self):
        result = self.runner.execute(
            action="run",
            command="format c:",
            image="alpine"
        )
        self.assertFalse(result.success)
        self.assertIn("Aislamiento de seguridad", result.error)

    def test_smolfile_generator(self):
        target = self.temp_dir / "Smolfile"
        result = self.generator.execute(
            image="python:3.12-alpine",
            target_path=str(target),
            cpus=4,
            memory_mib=2048,
            network=True
        )
        self.assertTrue(result.success)
        self.assertTrue(target.exists())
        content = target.read_text(encoding="utf-8")
        self.assertIn('image = "python:3.12-alpine"', content)
        self.assertIn("cpus = 4", content)
        self.assertIn("memory = 2048", content)
        self.assertIn("network = true", content)


if __name__ == "__main__":
    unittest.main()
