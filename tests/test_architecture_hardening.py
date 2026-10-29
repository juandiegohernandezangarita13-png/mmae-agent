"""
Suite de Pruebas Automatizadas para el Blindaje y Refactorización Arquitectónica de JEV:
1. Loop & Cycle Detector en el bucle ReAct (Detección de 3 llamadas consecutivas y MAX_ITERATIONS)
2. Validación Estricta con AST en DynamicToolManager (BaseTool inheritance, llamadas de riesgo y contención)
3. Control de Calidad, Esquema y Mitigación de Context Poisoning en evaluator.py y memory.py
4. Control de Ejecución Segura, Timeouts Estrictos y Truncamiento en code_runner.py
"""
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import json
import os
import sys

from jev.core.agent import AgentCore
from jev.core.llm_client import LLMResponse
from jev.tools.base import ToolRegistry, BaseTool, ToolResult
from jev.tools.dynamic_loader import DynamicToolManager, ToolSecurityASTValidator
from jev.core.memory import HierarchicalMemory
from jev.self_improvement.evaluator import SelfImprovementEvaluator
from jev.tools.code_runner import PythonRunnerTool, ShellCommandTool, MAX_OUTPUT_CHARS, MAX_EXECUTION_TIMEOUT
from jev.config import AgentConfig


class TestDummyTool(BaseTool):
    name = "dummy_action"
    description = "Herramienta dummy para pruebas"
    parameters = {"type": "object", "properties": {"target": {"type": "string"}}}

    def execute(self, target: str = "default", **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Ejecutado sobre {target}")


class TestLoopAndCycleDetector(unittest.TestCase):
    """Pruebas del detector de ciclos repetitivos en agent.py."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(TestDummyTool())
        self.config = AgentConfig(max_iterations=5)
        self.agent = AgentCore(config=self.config, registry=self.registry)

    def test_cycle_detector_interrupts_third_consecutive_call(self):
        """
        Si el agente invoca la misma herramienta con los mismos argumentos 3 veces consecutivas:
        1. Debe interrumpir la llamada redundante.
        2. Debe inyectar la observación de sistema exacta.
        """
        tc = {
            "id": "call_loop_1",
            "name": "dummy_action",
            "arguments": {"target": "same_target"}
        }

        call_step = 0

        def mock_chat(*args, **kwargs):
            nonlocal call_step
            if not kwargs.get("tools"):
                return LLMResponse(content='[{"id": 1, "title": "Loop Test", "description": "Test", "expected_verification": "ok", "dependencies": []}]')
            call_step += 1
            if call_step <= 3:
                return LLMResponse(content="", tool_calls=[tc])
            else:
                return LLMResponse(content="Plan modificado tras alerta de ciclo.", tool_calls=[])

        self.agent.llm.chat = MagicMock(side_effect=mock_chat)

        res = self.agent.run_task("Ejecutar acción repetitiva")

        # Verificar observaciones de herramientas en el historial
        tool_msgs = [m for m in self.agent.messages if m.get("role") == "tool"]
        self.assertGreaterEqual(len(tool_msgs), 3)

        # El tercer mensaje de herramienta debe contener la observación de ciclo repetitivo
        expected_warning = "[SISTEMA: Ciclo repetitivo detectado. Tu acción anterior no produjo un cambio de estado. Debes cambiar de estrategia o reportar bloqueo.]"
        has_cycle_warning = any(expected_warning in m.get("content", "") for m in tool_msgs)
        self.assertTrue(has_cycle_warning, f"No se encontró la advertencia de ciclo esperada en: {tool_msgs}")

    def test_max_iterations_limit_halts_infinite_loop(self):
        """Verifica que se respete el límite configurable MAX_ITERATIONS deteniendo la tarea."""
        tc = {
            "id": "call_inf",
            "name": "dummy_action",
            "arguments": {"target": "infinite"}
        }

        # Siempre devuelve tool_call obligando a iterar
        self.agent.llm.chat = MagicMock(return_value=LLMResponse(content="", tool_calls=[tc]))

        res = self.agent.run_task("Tarea infinita")
        self.assertTrue(
            "MAX_ITERATIONS" in res or "ACCION CANCELADA" in res or "límite" in res.lower(),
            f"La respuesta debe indicar detención por límite de iteraciones o cancelación de ciclo: {res}"
        )


class TestASTValidationDynamicLoader(unittest.TestCase):
    """Pruebas de la validación sintáctica y de seguridad con AST en dynamic_loader.py."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.manager = DynamicToolManager(self.registry)

    def test_valid_basetool_subclass_passes_ast_validation(self):
        valid_code = """
from jev.tools.base import BaseTool, ToolResult

class ValidCustomTool(BaseTool):
    name = "valid_custom_tool"
    description = "Herramienta válida de prueba"
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="OK")
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(valid_code)
        self.assertTrue(is_safe)
        self.assertIsNone(error_msg)

    def test_missing_basetool_subclass_fails_validation(self):
        code_without_basetool = """
class StandaloneHelper:
    def execute(self):
        return "Hola"
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(code_without_basetool)
        self.assertFalse(is_safe)
        self.assertIn("BaseTool", error_msg)

    def test_syntax_error_fails_validation(self):
        bad_syntax = "def broken_code( : invalid"
        is_safe, error_msg = ToolSecurityASTValidator.validate(bad_syntax)
        self.assertFalse(is_safe)
        self.assertIn("sintaxis", error_msg.lower())

    def test_prohibited_os_system_call_fails_validation(self):
        dangerous_code = """
import os
from jev.tools.base import BaseTool, ToolResult

class DangerousTool(BaseTool):
    name = "dangerous_tool"
    description = "Herramienta con llamadas prohibidas"
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        os.system("echo Peligro")
        return ToolResult(success=True, output="Done")
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(dangerous_code)
        self.assertFalse(is_safe)
        self.assertIn("os.system", error_msg)

    def test_prohibited_from_os_import_system_fails_validation(self):
        dangerous_code = """
from os import system
from jev.tools.base import BaseTool, ToolResult

class DangerousImportTool(BaseTool):
    name = "dangerous_import_tool"
    description = "Herramienta con importación prohibida"
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        system("dir")
        return ToolResult(success=True, output="Done")
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(dangerous_code)
        self.assertFalse(is_safe)
        self.assertIn("system", error_msg)

    def test_prohibited_ctypes_kernel_call_fails_validation(self):
        ctypes_code = """
import ctypes
from jev.tools.base import BaseTool, ToolResult

class CtypesTool(BaseTool):
    name = "ctypes_tool"
    description = "Herramienta con ctypes"
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        ctypes.windll.kernel32.GetTickCount()
        return ToolResult(success=True, output="Done")
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(ctypes_code)
        self.assertFalse(is_safe)
        self.assertIn("ctypes", error_msg)

    def test_prohibited_tampering_of_protected_jev_modules_fails_validation(self):
        tamper_code = """
import sys
from jev.tools.base import BaseTool, ToolResult

class HijackTool(BaseTool):
    name = "hijack_tool"
    description = "Secuestro de módulo protegido"
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolResult:
        sys.modules["jev.core.agent"] = None
        return ToolResult(success=True, output="Done")
"""
        is_safe, error_msg = ToolSecurityASTValidator.validate(tamper_code)
        self.assertFalse(is_safe)
        self.assertIn("módulo protegido", error_msg)


class TestLessonsQualityAndContextPoisoning(unittest.TestCase):
    """Pruebas del nuevo esquema de lecciones y mitigación de context poisoning."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = HierarchicalMemory(memory_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lesson_schema_structure(self):
        """Verifica que las lecciones creadas tengan el esquema formal con UUID/hash, times_applied y success_rate."""
        entry = self.memory.add_learned_lesson(
            trigger_context="Shell",
            lesson="Usar siempre rutas absolutas con forward slashes para evitar problemas de escape en Windows.",
            context="Tarea de consola"
        )

        self.assertIn("id", entry)
        self.assertTrue(entry["id"].startswith("lesson_"))
        self.assertEqual(entry["trigger_context"], "Shell")
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["times_applied"], 0)
        self.assertEqual(entry["success_rate"], 1.0)
        self.assertIn("created_at", entry)

    def test_anti_duplication_prevents_context_poisoning(self):
        """Añadir la misma lección no debe crear duplicados, sino reforzar su uso."""
        rule_text = "Verificar existencia de archivo antes de ejecutar lectura o parche."
        entry1 = self.memory.add_learned_lesson(trigger_context="Archivos", lesson=rule_text)
        entry2 = self.memory.add_learned_lesson(trigger_context="Archivos", lesson=rule_text)

        all_lessons = self.memory.get_all_lessons()
        matching = [l for l in all_lessons if l.get("lesson") == rule_text]
        self.assertEqual(len(matching), 1, "No debe duplicarse la misma lección en disco")
        self.assertEqual(matching[0]["times_applied"], 1)

    def test_ttl_and_outcome_update_deactivates_low_performance_lessons(self):
        """Si una regla falla repetidamente (< 40% de éxito), se marca como inactiva."""
        rule_text = "Regla experimental que resultó ineficaz o engañosa"
        entry = self.memory.add_learned_lesson(trigger_context="Estrategia", lesson=rule_text)
        lesson_id = entry["id"]

        # Simular 3 fallos consecutivos
        self.memory.update_lesson_outcome(lesson_id, task_success=False)
        self.memory.update_lesson_outcome(lesson_id, task_success=False)
        self.memory.update_lesson_outcome(lesson_id, task_success=False)

        updated_lessons = self.memory.get_all_lessons(include_inactive=True)
        target = [l for l in updated_lessons if l["id"] == lesson_id][0]
        self.assertEqual(target["status"], "inactive")
        self.assertLess(target["success_rate"], 0.4)

        # Verificar que get_lessons_prompt NO la incluye en el System Prompt
        prompt = self.memory.get_lessons_prompt()
        self.assertNotIn(rule_text, prompt)


class TestCodeRunnerSecurityAndTimeouts(unittest.TestCase):
    """Pruebas de ejecución segura, terminación de procesos y truncamiento en code_runner.py."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.py_tool = PythonRunnerTool(workspace_dir=Path(self.temp_dir))
        self.cmd_tool = ShellCommandTool(workspace_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_python_runner_execution_and_clean_exit(self):
        res = self.py_tool.execute(code="print('Hello Safe World')")
        self.assertTrue(res.success)
        self.assertIn("Hello Safe World", res.output)

    def test_python_runner_timeout_cancels_hanging_script(self):
        res = self.py_tool.execute(code="import time; time.sleep(10)", timeout=1)
        self.assertFalse(res.success)
        self.assertIn("timeout", res.error.lower())

    def test_output_truncation_limits_memory_bloat(self):
        # Generar salida que exceda MAX_OUTPUT_CHARS
        huge_code = f"print('A' * {MAX_OUTPUT_CHARS + 2000})"
        res = self.py_tool.execute(code=huge_code)
        self.assertTrue(res.success)
        self.assertIn("SALIDA TRUNCADA", res.output)
        self.assertLessEqual(len(res.output), MAX_OUTPUT_CHARS + 500)

    def test_destructive_code_blocked_preventively(self):
        dangerous_py = "import shutil; shutil.rmtree('C:\\\\')"
        res = self.py_tool.execute(code=dangerous_py)
        self.assertFalse(res.success)
        self.assertIn("Bloqueo de seguridad", res.error)


if __name__ == "__main__":
    unittest.main()
