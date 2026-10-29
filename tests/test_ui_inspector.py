"""
Suite de pruebas unitarias para UIInspectorTool (Windows UI Automation).
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jev.tools.ui_inspector import UIInspectorTool
from jev.tools import build_default_registry


class TestUIInspectorTool(unittest.TestCase):

    def setUp(self):
        self.tool = UIInspectorTool()

    def test_01_registry_integration(self):
        """Verifica que la herramienta esté correctamente registrada en el registro por defecto."""
        registry, _ = build_default_registry()
        registered_tool = registry.get("inspect_screen_ui")
        self.assertIsNotNone(registered_tool)
        self.assertEqual(registered_tool.name, "inspect_screen_ui")
        self.assertIn("max_elements", registered_tool.parameters["properties"])
        self.assertIn("search_text", registered_tool.parameters["properties"])
        self.assertIn("clickable_only", registered_tool.parameters["properties"])

    def test_02_live_desktop_inspection(self):
        """Prueba la ejecución real en el entorno Windows."""
        res = self.tool.execute(max_elements=10, only_focused_window=False)
        self.assertTrue(res.success)
        self.assertIn("total_elements", res.data)
        self.assertIsInstance(res.data["elements"], list)
        self.assertIn("WINDOWS UI INSPECTION", res.output)

    def test_03_search_text_filtering(self):
        """Prueba la búsqueda con un filtro inexistente sin producir errores."""
        res = self.tool.execute(max_elements=10, search_text="NONEXISTENT_ELEMENT_XYZ_9999")
        self.assertTrue(res.success)
        self.assertEqual(res.data["total_elements"], 0)
        self.assertIn("No se detectaron controles coincidentes", res.output)

    def test_04_mocked_controls_traversal(self):
        """Prueba el recorrido recursivo, clasificación de botones clickeables y coordenadas."""
        mock_rect = MagicMock()
        mock_rect.width.return_value = 120
        mock_rect.height.return_value = 40
        mock_rect.xcenter.return_value = 500
        mock_rect.ycenter.return_value = 300
        mock_rect.left = 440
        mock_rect.top = 280
        mock_rect.right = 560
        mock_rect.bottom = 320

        # Control hijo 1: Botón "Guardar"
        mock_btn = MagicMock()
        mock_btn.NativeWindowHandle = 1001
        mock_btn.BoundingRectangle = mock_rect
        mock_btn.Name = "Guardar Archivo"
        mock_btn.ControlTypeName = "ButtonControl"
        mock_btn.GetChildren.return_value = []

        # Control raíz
        mock_root = MagicMock()
        mock_root.NativeWindowHandle = 1000
        mock_root.Name = "Editor Principal"
        mock_root.BoundingRectangle = mock_rect
        mock_root.ControlTypeName = "WindowControl"
        mock_root.GetChildren.return_value = [mock_btn]

        mock_auto = MagicMock()
        mock_auto.GetForegroundControl.return_value = mock_root
        mock_auto.SetGlobalSearchTimeout = MagicMock()

        with patch.dict("sys.modules", {"uiautomation": mock_auto}):
            res = self.tool.execute(max_elements=10, only_focused_window=True, clickable_only=True)
            self.assertTrue(res.success)
            self.assertEqual(len(res.data["elements"]), 1)
            el = res.data["elements"][0]
            self.assertEqual(el["type"], "ButtonControl")
            self.assertEqual(el["text"], "Guardar Archivo")
            self.assertEqual(el["center_x"], 500)
            self.assertEqual(el["center_y"], 300)
            self.assertTrue(el["is_actionable"])

    def test_05_fallback_chain_when_foreground_none(self):
        """Verifica que si GetForegroundControl retorna None, recurra a GetFocusedControl o GetRootControl."""
        mock_rect = MagicMock()
        mock_rect.width.return_value = 100
        mock_rect.height.return_value = 30
        mock_rect.xcenter.return_value = 200
        mock_rect.ycenter.return_value = 150
        mock_rect.left = 150
        mock_rect.top = 135
        mock_rect.right = 250
        mock_rect.bottom = 165

        mock_fallback_root = MagicMock()
        mock_fallback_root.NativeWindowHandle = 2000
        mock_fallback_root.Name = "Fallback Window"
        mock_fallback_root.BoundingRectangle = mock_rect
        mock_fallback_root.ControlTypeName = "WindowControl"
        mock_fallback_root.GetChildren.return_value = []

        mock_auto = MagicMock()
        mock_auto.GetForegroundControl.return_value = None
        mock_auto.GetFocusedControl.return_value = None
        mock_auto.GetRootControl.return_value = mock_fallback_root

        with patch.dict("sys.modules", {"uiautomation": mock_auto}):
            res = self.tool.execute(only_focused_window=True)
            self.assertTrue(res.success)
            self.assertEqual(res.data["window_title"], "Fallback Window")


if __name__ == "__main__":
    unittest.main()
