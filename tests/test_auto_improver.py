"""
Pruebas unitarias para el sistema de auto-mejora asistido por Gemini (GeminiSelfImprover).
"""
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from jev.tools.base import ToolRegistry, BaseTool, ToolResult
from jev.core.auto_improver import GeminiSelfImprover
from jev.tools.gemini_improver import ConsultGeminiAndSelfImproveTool
from jev.config import AgentConfig


class TestGeminiSelfImprover(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "generated_tools"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir = Path(self.temp_dir) / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.config = AgentConfig(
            base_dir=Path(self.temp_dir),
            memory_dir=self.memory_dir,
            workspace_dir=Path(self.temp_dir)
        )
        self.registry = ToolRegistry()

        # Mock LLM Client
        self.mock_llm = MagicMock()

        self.improver = GeminiSelfImprover(
            registry=self.registry,
            config=self.config,
            llm_client=self.mock_llm,
            output_dir=self.output_dir
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_system_inventory(self):
        inventory = self.improver.build_system_inventory()
        self.assertIn("total_registered_tools", inventory)
        self.assertIn("tools", inventory)
        self.assertIn("core_subsystems", inventory)
        self.assertIn("existing_generated_tools", inventory)

    def test_consult_gemini_with_mocked_llm(self):
        fake_response = MagicMock()
        fake_response.content = """{
            "diagnosis": "JEV carece de una herramienta para medir latencia de red y ping.",
            "recommended_capability": "Network Ping Latency",
            "tool_name": "network_latency_probe_tool",
            "class_name": "NetworkLatencyProbeTool",
            "description": "Mide la latencia de red y disponibilidad de un host.",
            "required_dependencies": [],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Host o IP objetivo"}
                },
                "required": ["host"]
            },
            "python_code": "from jev.tools.base import BaseTool, ToolResult\\n\\nclass NetworkLatencyProbeTool(BaseTool):\\n    name = 'network_latency_probe_tool'\\n    description = 'Mide latencia'\\n    parameters = {'type': 'object', 'properties': {'host': {'type': 'string'}}}\\n    def execute(self, host: str = '127.0.0.1', **kwargs) -> ToolResult:\\n        return ToolResult(success=True, output=f'Ping a {host}: 1ms', data={'host': host, 'rtt_ms': 1})\\n"
        }"""
        self.mock_llm.chat.return_value = fake_response

        proposal = self.improver.consult_gemini(focus_area="network")
        self.assertEqual(proposal["tool_name"], "network_latency_probe_tool")
        self.assertEqual(proposal["class_name"], "NetworkLatencyProbeTool")
        self.assertIn("NetworkLatencyProbeTool", proposal["python_code"])

    def test_synthesize_and_hot_reload_live_injection(self):
        proposal = {
            "diagnosis": "Falta herramienta de prueba",
            "recommended_capability": "Test Tool",
            "tool_name": "unit_test_probe_tool",
            "class_name": "UnitTestProbeTool",
            "description": "Herramienta sintética para validar hot reloading",
            "required_dependencies": [],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["ping"]}
                }
            },
            "python_code": """
from jev.tools.base import BaseTool, ToolResult

class UnitTestProbeTool(BaseTool):
    name = "unit_test_probe_tool"
    description = "Herramienta sintética para validar hot reloading"
    parameters = {"type": "object", "properties": {"action": {"type": "string"}}}

    def execute(self, action: str = "ping", **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Probe OK con action={action}", data={"status": "live"})
"""
        }

        # Ejecutar síntesis y hot reloading
        result = self.improver.synthesize_and_hot_reload(proposal)
        self.assertTrue(result["success"], msg=result.get("error"))
        self.assertEqual(result["tool_name"], "unit_test_probe_tool")

        # Comprobar que fue inyectada en ToolRegistry sin reiniciar
        injected = self.registry.get("unit_test_probe_tool")
        self.assertIsNotNone(injected)

        # Probar ejecución directa de la herramienta recién inyectada
        exec_res = injected.execute(action="ping")
        self.assertTrue(exec_res.success)
        self.assertIn("Probe OK", exec_res.output)

    def test_consult_gemini_and_self_improve_tool_wrapper(self):
        fake_response = MagicMock()
        fake_response.content = """{
            "diagnosis": "Falta herramienta de portapapeles",
            "recommended_capability": "Clipboard",
            "tool_name": "test_clipboard_tool",
            "class_name": "TestClipboardTool",
            "description": "Herramienta de portapapeles para pruebas",
            "required_dependencies": [],
            "parameters_schema": {"type": "object", "properties": {}},
            "python_code": "from jev.tools.base import BaseTool, ToolResult\\n\\nclass TestClipboardTool(BaseTool):\\n    name = 'test_clipboard_tool'\\n    description = 'Test Clipboard'\\n    parameters = {'type': 'object', 'properties': {}}\\n    def execute(self, **kwargs) -> ToolResult:\\n        return ToolResult(success=True, output='Clipboard read OK', data={})\\n"
        }"""
        self.mock_llm.chat.return_value = fake_response

        tool = ConsultGeminiAndSelfImproveTool(
            improver=self.improver,
            registry=self.registry,
            config=self.config
        )

        # Modo dry run
        dry_res = tool.execute(dry_run=True)
        self.assertTrue(dry_res.success)
        self.assertIn("MODO DIAGNÓSTICO", dry_res.output)

        # Modo live run
        live_res = tool.execute(dry_run=False)
        self.assertTrue(live_res.success)
        self.assertIn("AUTO-MEJORA CONCLUIDA CON ÉXITO", live_res.output)
        self.assertIsNotNone(self.registry.get("test_clipboard_tool"))


if __name__ == "__main__":
    unittest.main()
