"""
Suite de Pruebas Automatizadas para la Integración de Free-Claude-Code en JEV:
1. Gestor de Ciclo de Vida y Proceso (FreeClaudeCodeService)
2. Adaptador y Puente Anthropic Messages API (ClaudeCodeBridge)
3. Herramienta Customizada y Acciones (ClaudeCodeTool / skill_claude_code)
4. Cableado en el Núcleo de JEV (AgentConfig, LLM Client y Tool Registry)
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import tempfile
import shutil
import os

from jev.core.claude_code_service import FreeClaudeCodeService
from jev.core.claude_code_bridge import ClaudeCodeBridge, ClaudeCodeResponse, CodeSnippet
from jev.tools.custom.skill_claude_code import ClaudeCodeTool
from jev.tools import build_default_registry
from jev.config import AgentConfig, BASE_DIR
from jev.core.llm_client import LocalLLMClient


class TestFreeClaudeCodeService(unittest.TestCase):
    """Pruebas del servicio supervisor en segundo plano de Free-Claude-Code."""

    def setUp(self):
        self.service = FreeClaudeCodeService()

    def test_singleton_instance(self):
        service2 = FreeClaudeCodeService()
        self.assertIs(self.service, service2, "FreeClaudeCodeService debe ser un Singleton")

    def test_binary_paths_resolution(self):
        self.assertTrue(self.service.venv_python.name.startswith("python"))
        self.assertTrue(self.service.fcc_server_bin.name.startswith("fcc-server"))
        self.assertTrue(self.service.repo_dir.exists(), "El directorio repo_dir de FCC debe existir")

    def test_base_url_and_port(self):
        self.assertEqual(self.service.base_url, f"http://127.0.0.1:{self.service.port}")
        self.assertIsInstance(self.service.port, int)

    def test_get_status_structure(self):
        status = self.service.get_status()
        self.assertIn("is_running", status)
        self.assertIn("is_healthy", status)
        self.assertIn("port", status)
        self.assertIn("base_url", status)
        self.assertIn("default_model", status)
        self.assertIn("has_api_key", status)
        self.assertIn("log_file", status)

    @patch("urllib.request.urlopen")
    def test_is_healthy_mocked(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        self.assertTrue(self.service.is_healthy())

    def test_update_config_in_memory(self):
        old_model = self.service.default_model
        test_key = "sk-or-v1-mock-test-key-12345"
        test_model = "open_router/meta-llama/llama-3.3-70b-instruct:free"

        self.service.update_config(openrouter_api_key=test_key, default_model=test_model)
        self.assertEqual(self.service.openrouter_api_key, test_key)
        self.assertEqual(self.service.default_model, test_model)

        # Restaurar modelo
        self.service.update_config(default_model=old_model)


class TestClaudeCodeBridge(unittest.TestCase):
    """Pruebas del cliente puente con la Messages API de Claude Code."""

    def setUp(self):
        self.bridge = ClaudeCodeBridge()

    def test_extract_code_blocks_and_filenames(self):
        sample_text = (
            "Aquí está la solución solicitada:\n\n"
            "```python\n"
            "# file: utils/calculator.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n\n"
            "Y este es el componente React:\n"
            "```javascript\n"
            "// file: components/App.jsx\n"
            "export default function App() {\n"
            "  return <div>Hola</div>;\n"
            "}\n"
            "```"
        )
        blocks = self.bridge._extract_code_blocks(sample_text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].language, "python")
        self.assertIn("def add", blocks[0].code)
        self.assertEqual(blocks[0].filename, "utils/calculator.py")
        self.assertEqual(blocks[1].language, "javascript")
        self.assertEqual(blocks[1].filename, "components/App.jsx")

    def test_parse_response_with_thinking(self):
        raw_anthropic = {
            "model": "open_router/anthropic/claude-3.5-sonnet",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Paso 1: Planificar arquitectura modular. Paso 2: Generar código limpio."
                },
                {
                    "type": "text",
                    "text": "```python\nprint('Operación completada')\n```"
                }
            ],
            "usage": {
                "input_tokens": 150,
                "output_tokens": 45
            }
        }
        parsed = self.bridge._parse_anthropic_response(raw_anthropic)
        self.assertTrue(parsed.is_success)
        self.assertIn("Planificar arquitectura modular", parsed.thinking)
        self.assertIn("Operación completada", parsed.content)
        self.assertEqual(len(parsed.code_blocks), 1)
        self.assertEqual(parsed.usage.get("output_tokens"), 45)

    @patch("jev.core.claude_code_service.FreeClaudeCodeService.ensure_running")
    @patch("urllib.request.urlopen")
    def test_send_message_mocked(self, mock_urlopen, mock_ensure):
        mock_ensure.return_value = (True, "Servicio activo")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "model": "open_router/anthropic/claude-3.5-sonnet",
            "content": [{"type": "text", "text": "Respuesta desde mock de Claude Code"}],
            "usage": {"input_tokens": 10, "output_tokens": 20}
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = self.bridge.send_message(
            messages=[{"role": "user", "content": "¿Cómo estás?"}],
            system="Eres un asistente"
        )
        self.assertTrue(res.is_success)
        self.assertIn("Respuesta desde mock", res.content)


class TestClaudeCodeTool(unittest.TestCase):
    """Pruebas funcionales de la herramienta ClaudeCodeTool."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tool = ClaudeCodeTool(workspace_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tool_metadata_and_parameters(self):
        self.assertEqual(self.tool.name, "skill_claude_code")
        self.assertIn("action", self.tool.parameters["properties"])
        self.assertIn("server_status", self.tool.parameters["properties"]["action"]["enum"])
        self.assertIn("generate_code", self.tool.parameters["properties"]["action"]["enum"])

    def test_action_server_status(self):
        result = self.tool.execute(action="server_status")
        self.assertTrue(result.success)
        self.assertIn("Estado de Free-Claude-Code Proxy", result.output)
        self.assertIn("Puerto:", result.output)
        self.assertIn("Endpoint Base:", result.output)

    def test_action_configure(self):
        result = self.tool.execute(
            action="configure",
            openrouter_key="sk-or-v1-testkey12345",
            model="open_router/meta-llama/llama-3.3-70b-instruct:free"
        )
        self.assertTrue(result.success)
        self.assertIn("Configuración de Claude Code actualizada", result.output)
        self.assertEqual(self.tool.service.default_model, "open_router/meta-llama/llama-3.3-70b-instruct:free")

    @patch.object(ClaudeCodeBridge, "send_message")
    def test_action_query_mocked(self, mock_send):
        mock_send.return_value = ClaudeCodeResponse(
            content="Solución técnica de alto nivel.",
            thinking="Análisis de complejidad O(1).",
            model="open_router/anthropic/claude-3.5-sonnet",
            is_success=True
        )
        result = self.tool.execute(action="query", prompt="Explica la arquitectura de microservicios")
        self.assertTrue(result.success)
        self.assertIn("Solución técnica de alto nivel", result.output)
        self.assertIn("Análisis de complejidad", result.output)

    @patch.object(ClaudeCodeBridge, "send_message")
    def test_action_generate_code_saves_file(self, mock_send):
        generated_py = "def hello_world():\n    return 'Hello from Claude Code'\n"
        mock_send.return_value = ClaudeCodeResponse(
            content=f"```python\n{generated_py}```",
            thinking="Implementación directa.",
            code_blocks=[CodeSnippet(language="python", code=generated_py)],
            is_success=True
        )

        output_rel_path = "src/greetings.py"
        result = self.tool.execute(
            action="generate_code",
            prompt="Genera una función hello_world",
            language="python",
            output_path=output_rel_path
        )
        self.assertTrue(result.success)
        self.assertTrue("greetings.py" in result.output)

        # Verificar que el archivo se guardó físicamente en el workspace temporal
        saved_file = Path(self.temp_dir) / output_rel_path
        self.assertTrue(saved_file.exists())
        self.assertEqual(saved_file.read_text(encoding="utf-8").strip(), generated_py.strip())

    def test_invalid_action_handling(self):
        result = self.tool.execute(action="non_existent_action_xyz")
        self.assertFalse(result.success)
        self.assertIn("no reconocida", result.error)


class TestClaudeCodeSystemWiring(unittest.TestCase):
    """Verifica que Claude Code esté integrado en el registro global, config y habilidades."""

    def test_tool_present_in_default_registry(self):
        registry, _ = build_default_registry()
        tool = registry.get("skill_claude_code")
        self.assertIsNotNone(tool, "skill_claude_code debe estar registrada en default tool registry")
        self.assertEqual(tool.name, "skill_claude_code")

    def test_skill_directory_packaged_properly(self):
        skill_meta_file = Path(BASE_DIR) / "jev" / "skills" / "skill_claude_code" / "metadata.json"
        self.assertTrue(skill_meta_file.exists(), "metadata.json de la skill debe existir")
        with open(skill_meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("name"), "skill_claude_code")
        self.assertEqual(data.get("category"), "code_engineering")

        skill_handler = Path(BASE_DIR) / "jev" / "skills" / "skill_claude_code" / "handler.py"
        self.assertTrue(skill_handler.exists(), "handler.py de la skill debe existir")

    def test_agent_config_has_claude_code_attributes(self):
        cfg = AgentConfig()
        self.assertTrue(hasattr(cfg, "fcc_base_url"))
        self.assertTrue(hasattr(cfg, "fcc_model"))
        self.assertTrue(hasattr(cfg, "openrouter_api_key"))
        self.assertEqual(cfg.fcc_base_url, "http://127.0.0.1:8082")

    @patch("jev.core.claude_code_bridge.ClaudeCodeBridge.send_message")
    def test_llm_client_routes_to_claude_code_provider(self, mock_send):
        mock_send.return_value = ClaudeCodeResponse(
            content="Respuesta del LLM desde Claude Code Provider",
            model="open_router/anthropic/claude-3.5-sonnet",
            is_success=True
        )

        cfg = AgentConfig(llm_provider="claude_code")
        client = LocalLLMClient(config=cfg)
        response_obj = client.chat(messages=[{"role": "user", "content": "Hola"}])

        self.assertIn("Respuesta del LLM desde Claude Code Provider", response_obj.content)
        mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
