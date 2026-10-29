"""
Suite de Pruebas Automatizadas para la Integración Visual y de UI de Free-Claude-Code:
1. Verificación de presencia y estructura de elementos visuales en jarvis.html
2. Métodos del puente JarvisBridge en app.py (get_fcc_status, start_fcc_server, restart_fcc_server, query_claude_code, get_telemetry)
3. Sincronización de telemetría y callbacks bidireccionales
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app import JarvisBridge
from jev.config import AgentConfig


class TestFccUiIntegration(unittest.TestCase):
    """Pruebas de la integración visual y de backend de Free Claude Code en la UI."""

    def setUp(self):
        self.config = AgentConfig()
        self.bridge = JarvisBridge(self.config)
        self.html_path = Path(__file__).parent.parent / "jev" / "ui" / "templates" / "jarvis.html"

    def test_jarvis_html_contains_fcc_elements(self):
        """Verifica que la plantilla HTML posea todos los componentes visuales e interactivos de FCC."""
        self.assertTrue(self.html_path.exists(), "jarvis.html debe existir")
        content = self.html_path.read_text(encoding="utf-8")

        # Insignia y botón en cabecera
        self.assertIn('id="fccStatusBadge"', content)
        self.assertIn('id="fccBadgeText"', content)
        self.assertIn('id="fccPulseDot"', content)
        self.assertIn('id="btnFccToggle"', content)

        # Tab y contenedor en panel de artefactos
        self.assertIn('id="tabFcc"', content)
        self.assertIn('id="viewFcc"', content)
        self.assertIn('switchArtifactTab(\'fcc\')', content)
        self.assertIn('openFccTab()', content)

        # Consola interactiva y tarjetas de estado
        self.assertIn('id="fccChipState"', content)
        self.assertIn('id="fccCardStatus"', content)
        self.assertIn('id="fccPromptInput"', content)
        self.assertIn('id="btnFccSubmit"', content)
        self.assertIn('id="fccResponseContainer"', content)

        # Funciones JavaScript de control y sincronización
        self.assertIn('function updateFccUi(', content)
        self.assertIn('function refreshFccStatus(', content)
        self.assertIn('function submitFccQuery(', content)
        self.assertIn('window.onUpdateFCCStatus', content)

    def test_bridge_get_fcc_status(self):
        """Verifica que el puente obtenga correctamente el estado estructurado del servicio."""
        status = self.bridge.get_fcc_status()
        self.assertIsInstance(status, dict)
        self.assertIn("is_running", status)
        self.assertIn("is_healthy", status)
        self.assertIn("port", status)
        self.assertEqual(status["port"], 8082)

    @patch("jev.core.claude_code_bridge.ClaudeCodeBridge.query")
    def test_bridge_query_claude_code(self, mock_query):
        """Verifica el despacho de prompts a Claude Code desde la UI."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = "```python\nprint('Hola Claude')\n```"
        mock_response.thinking = "Analizando solicitud..."
        mock_response.model = "open_router/meta-llama/llama-3.3-70b-instruct:free"
        mock_response.error = None
        mock_snippet = MagicMock()
        mock_snippet.language = "python"
        mock_snippet.code = "print('Hola Claude')"
        mock_snippet.filename = None
        mock_response.code_blocks = [mock_snippet]
        mock_query.return_value = mock_response

        res = self.bridge.query_claude_code("Haz un hello world")
        self.assertTrue(res["success"])
        self.assertIn("print('Hola Claude')", res["content"])
        self.assertEqual(res["thinking"], "Analizando solicitud...")
        self.assertEqual(len(res["code_snippets"]), 1)
        self.assertEqual(res["code_snippets"][0]["code"], "print('Hola Claude')")

    def test_bridge_get_telemetry_includes_fcc(self):
        """Verifica que get_telemetry() exponga las métricas de Free Claude Code."""
        telemetry = self.bridge.get_telemetry()
        self.assertIn("fcc_healthy", telemetry)
        self.assertIn("fcc_running", telemetry)
        self.assertIn("fcc_port", telemetry)
        self.assertIn("fcc_model", telemetry)
        self.assertEqual(telemetry["fcc_port"], 8082)


if __name__ == "__main__":
    unittest.main()
