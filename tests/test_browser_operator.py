"""
Suite de Pruebas Unitarias para el Subsistema de Navegación y Automatización Web Visual (Browser-Use Engine):
1. Control interactivo de navegación, DOM y captura visual (BrowserOperatorTool).
2. Interacción con elementos por índice visual, clics y tipeo con submit.
3. Extracción de datos estructurados y persistencia de cookies/sesión en disco.
4. Integración y enrutamiento reactivo hacia JarvisBridge (window.onRenderWebPreview).
5. Descubrimiento y ejecución modular en SkillRegistry y catálogo de herramientas de JEV.
"""
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock

from jev.tools.custom.skill_browser_use import BrowserOperatorTool, MockDomPage
from jev.tools.base import get_browser_operator_tool, ToolResult
from jev.skills.manager import SkillRegistry
from jev.config import AgentConfig
from app import JarvisBridge


class TestBrowserOperatorCore(unittest.TestCase):
    """Pruebas funcionales de navegación visual, interacción y extracción estructurada."""

    def setUp(self):
        self.tool = BrowserOperatorTool()

    def tearDown(self):
        self.tool.close_session()

    def test_navigate_and_capture_state(self):
        """Verifica navegación a una URL y generación de capturas visuales y volcado HTML."""
        res = self.tool.execute(action="navigate", url="https://news.ycombinator.com")
        self.assertTrue(res.success, f"Error en navigate: {res.error}")
        self.assertIn("url", res.data)
        self.assertIn("title", res.data)
        self.assertIn("screenshot", res.data)
        self.assertIn("html", res.data)

        screenshot_path = Path(res.data["screenshot"])
        self.assertTrue(screenshot_path.exists())
        self.assertGreater(screenshot_path.stat().st_size, 0)

        html_state_file = Path("data/browser_state/current_page.html")
        self.assertTrue(html_state_file.exists())
        self.assertGreater(html_state_file.stat().st_size, 0)

    def test_get_interactive_elements(self):
        """Verifica la indexación numérica de botones, enlaces y campos de entrada."""
        self.tool.execute(action="navigate", url="https://wikipedia.org")
        res = self.tool.execute(action="get_interactive_elements")
        self.assertTrue(res.success, f"Error en get_interactive_elements: {res.error}")
        self.assertIn("elements", res.data)
        elements = res.data["elements"]
        self.assertIsInstance(elements, list)
        self.assertGreater(len(elements), 0)

        first = elements[0]
        self.assertIn("index", first)
        self.assertIn("tag", first)
        self.assertIn("selector", first)

    def test_click_element_by_index_and_selector(self):
        """Verifica la ejecución de clic por índice visual o selector CSS."""
        self.tool.execute(action="navigate", url="https://example.com")
        self.tool.execute(action="get_interactive_elements")

        # Clic por índice
        res_idx = self.tool.execute(action="click_element", element_index=0)
        self.assertTrue(res_idx.success)
        self.assertEqual(res_idx.data.get("action"), "click")

        # Clic por selector
        res_sel = self.tool.execute(action="click_element", selector="#search_btn")
        self.assertTrue(res_sel.success)
        self.assertEqual(res_sel.data.get("action"), "click")

    def test_type_text_and_submit(self):
        """Verifica tipeo de texto con y sin envío (Enter)."""
        self.tool.execute(action="navigate", url="https://example.com")
        res = self.tool.execute(
            action="type_text",
            selector="#search_box",
            text="Autonomous Agent Architecture",
            submit=True
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("action"), "type")
        self.assertEqual(res.data.get("text_length"), len("Autonomous Agent Architecture"))

    def test_extract_structured_data(self):
        """Verifica la extracción estructurada de tablas y registros del DOM."""
        self.tool.execute(action="navigate", url="https://example.com/data")
        res = self.tool.execute(action="extract_structured_data")
        self.assertTrue(res.success)
        self.assertTrue("items" in res.data or "tables" in res.data)

    def test_capture_page_state(self):
        """Verifica la captura completa de estado bajo demanda."""
        self.tool.execute(action="navigate", url="https://example.com")
        res = self.tool.execute(action="capture_page_state")
        self.assertTrue(res.success)
        self.assertIn("url", res.data)
        self.assertIn("screenshot_path", res.data)
        self.assertIn("html", res.data)

    def test_close_session_lifecycle(self):
        """Verifica el cierre y limpieza del contexto de navegación."""
        self.tool.execute(action="navigate", url="https://example.com")
        res = self.tool.execute(action="close_session")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("status"), "closed")
        self.assertIsNone(BrowserOperatorTool._page)

    def test_error_missing_url(self):
        """Verifica manejo de errores cuando no se suministra URL para navegación."""
        res = self.tool.execute(action="navigate", url="")
        self.assertFalse(res.success)
        self.assertIn("url", res.error.lower())

    def test_error_unknown_action(self):
        """Verifica rechazo controlado de acciones desconocidas."""
        res = self.tool.execute(action="invalid_action_unknown")
        self.assertFalse(res.success)
        self.assertIn("desconocida", res.error.lower())


class TestBrowserOperatorJarvisIntegration(unittest.TestCase):
    """Pruebas de enrutamiento hacia la interfaz JarvisBridge."""

    def test_bridge_routes_browser_preview(self):
        """Verifica que el resultado de BrowserOperatorTool despache window.onRenderWebPreview."""
        config = AgentConfig()
        bridge = JarvisBridge(config)
        mock_window = MagicMock()
        bridge.set_window(mock_window)

        html_sample = "<!DOCTYPE html><html><body><h1>Browser Sandbox</h1></body></html>"
        tool_result = ToolResult(
            success=True,
            output="Navegación completada",
            data={
                "url": "https://test.local",
                "title": "Browser Live Preview",
                "html": html_sample
            }
        )

        bridge._on_tool_result("skill_browser_operator", tool_result)

        # Validar que evaluate_js fue llamado con onRenderWebPreview
        self.assertTrue(mock_window.evaluate_js.called)
        calls = [c[0][0] for c in mock_window.evaluate_js.call_args_list]
        preview_calls = [c for c in calls if "window.onRenderWebPreview" in c]
        self.assertGreater(len(preview_calls), 0)
        self.assertIn("Browser Live Preview", preview_calls[0])


class TestBrowserOperatorSkillRegistry(unittest.TestCase):
    """Pruebas de registro modular y ejecución desde SkillRegistry."""

    def test_skill_registry_discovers_browser_operator(self):
        """Verifica que el SkillRegistry descubra la habilidad modular skill_browser_operator."""
        registry = SkillRegistry()
        self.assertIn("skill_browser_operator", registry._skills)
        skill = registry.get_skill("skill_browser_operator")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.metadata.category, "web_automation")

    def test_skill_registry_executes_browser_operator(self):
        """Verifica la ejecución reflexiva a través del registro."""
        registry = SkillRegistry()
        res = registry.execute_skill(
            "skill_browser_operator",
            action="navigate",
            url="https://portal.local"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertIn("data", res)
        self.assertIn("html", res["data"])

    def test_factory_helper(self):
        """Verifica que get_browser_operator_tool() retorne una instancia válida de BrowserOperatorTool."""
        tool = get_browser_operator_tool()
        self.assertEqual(tool.name, "skill_browser_operator")
        self.assertEqual(tool.__class__.__name__, "BrowserOperatorTool")
        self.assertTrue(hasattr(tool, "execute"))


if __name__ == "__main__":
    unittest.main()
