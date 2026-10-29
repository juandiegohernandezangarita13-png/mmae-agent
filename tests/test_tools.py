"""
Suite de pruebas unitarias y de integración para las herramientas de JEV.
"""
import sys
from pathlib import Path

# Asegurar codificación UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import unittest
from jev.tools import build_default_registry
from jev.config import default_config


class TestJEVTools(unittest.TestCase):

    def setUp(self):
        self.registry, self.dynamic_mgr = build_default_registry()

    def test_01_screen_info(self):
        tool = self.registry.get("get_screen_info")
        self.assertIsNotNone(tool)
        res = tool.execute()
        self.assertTrue(res.success)
        self.assertIn("screen_width", res.data)
        self.assertGreater(res.data["screen_width"], 0)
        print("\n[OK] Test get_screen_info:", res.output.splitlines()[0])

    def test_02_screen_capture(self):
        tool = self.registry.get("take_screenshot")
        self.assertIsNotNone(tool)
        res = tool.execute(save_name="test_screenshot.png")
        self.assertTrue(res.success)
        self.assertTrue(Path(res.data["filepath"]).exists())
        print("[OK] Test take_screenshot:", res.output)

    def test_03_filesystem(self):
        # 1. Escribir archivo
        write_tool = self.registry.get("write_file")
        res_w = write_tool.execute(path="test_note.txt", content="Línea 1: Hola Mundo\nLínea 2: JEV en acción")
        self.assertTrue(res_w.success)

        # 2. Leer archivo
        read_tool = self.registry.get("read_file")
        res_r = read_tool.execute(path="test_note.txt")
        self.assertTrue(res_r.success)
        self.assertIn("Hola Mundo", res_r.output)

        # 3. Parchear archivo
        patch_tool = self.registry.get("patch_file")
        res_p = patch_tool.execute(path="test_note.txt", target_content="Hola Mundo", replacement_content="Hola IA Local")
        self.assertTrue(res_p.success)

        res_r2 = read_tool.execute(path="test_note.txt")
        self.assertIn("Hola IA Local", res_r2.output)
        print("[OK] Test filesystem (write, read, patch): Éxito")

    def test_04_code_runners(self):
        # Python runner
        py_tool = self.registry.get("execute_python")
        res_py = py_tool.execute(code="print(sum([i for i in range(1, 11)]))")
        self.assertTrue(res_py.success)
        self.assertIn("55", res_py.output)

        # Shell command
        cmd_tool = self.registry.get("execute_command")
        res_cmd = cmd_tool.execute(command="Write-Output 'JEV Online'")
        self.assertTrue(res_cmd.success)
        self.assertIn("JEV Online", res_cmd.output)
        print("[OK] Test code_runners (Python + PowerShell): Éxito")

    def test_05_web_search(self):
        web_tool = self.registry.get("search_web")
        res = web_tool.execute(query="Python programming language", max_results=2)
        self.assertTrue(res.success)
        self.assertGreater(len(res.output), 20)
        print("[OK] Test web_search:", res.output[:120].strip() + "...")

    def test_06_dynamic_tool_creation(self):
        # Creamos una herramienta personalizada en caliente
        custom_code = '''
from jev.tools.base import BaseTool, ToolResult

class WordCounterTool(BaseTool):
    name = "count_words"
    description = "Cuenta el numero de palabras en un texto."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto a analizar"}
        },
        "required": ["text"]
    }

    def execute(self, text: str, **kwargs) -> ToolResult:
        words = len(text.split())
        return ToolResult(success=True, output=f"Total de palabras: {words}", data={"words": words})
'''
        create_tool = self.registry.get("create_custom_tool")
        res_create = create_tool.execute(tool_filename="word_counter.py", python_code=custom_code)
        self.assertTrue(res_create.success)

        # Verificar que la nueva herramienta se registró automáticamente en el registry
        new_tool = self.registry.get("count_words")
        self.assertIsNotNone(new_tool)
        res_exec = new_tool.execute(text="JEV es un agente completamente automejorable")
        self.assertTrue(res_exec.success)
        self.assertEqual(res_exec.data["words"], 6)
    def test_07_github_tools(self):
        # 1. Búsqueda de repositorios
        search_tool = self.registry.get("search_github_repos")
        self.assertIsNotNone(search_tool)
        res_s = search_tool.execute(query="python agent", max_results=2)
        self.assertTrue(res_s.success)
        self.assertIn("Resultados de GitHub", res_s.output)

        # 2. Inspección de README
        inspect_tool = self.registry.get("inspect_github_repo")
        self.assertIsNotNone(inspect_tool)
        res_i = inspect_tool.execute(repo_full_name="psf/requests")
        self.assertTrue(res_i.success)
        self.assertGreater(res_i.data.get("length", 0), 100)
        print("[OK] Test github_tools (Search + Inspect README): Éxito")


if __name__ == "__main__":
    unittest.main()
