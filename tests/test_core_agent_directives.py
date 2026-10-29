"""
Pruebas unitarias para las Directivas Maestras del Núcleo del Agente (Core Agent Directives):
1. Autonomía estricta de ejecución (sin pausas intermedias ni transferir turno durante DAG)
2. Aislamiento de herramientas (Tool Calling Integrity y sanitización de esquemas JSON)
3. Preservación de contexto y prevención de regresión de código
4. Higiene de dependencias del entorno (validación de biblioteca estándar vs pip)
5. Estándares de ingeniería senior y persistencia en memoria SQLite
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jev.core.agent import AgentCore
from jev.core.llm_client import LLMResponse
from jev.core.planner import DAGPlanner
from jev.core.verifier import ActionVerifier
from jev.core.memory import HierarchicalMemory
from jev.tools.base import ToolRegistry, BaseTool, ToolResult
from jev.config import AgentConfig


class DummyTool(BaseTool):
    name = "execute_command"
    description = "Dummy command tool"
    parameters = {"type": "object", "properties": {"command": {"type": "string"}}}

    def execute(self, command: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Executed: {command}")


class TestCoreAgentDirectives(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True)
        self.memory_dir = self.temp_dir / "memory"
        self.memory_dir.mkdir(parents=True)

        self.config = AgentConfig(
            base_dir=self.temp_dir,
            workspace_dir=self.workspace_dir,
            memory_dir=self.memory_dir,
            max_iterations=10,
            hybrid_mode=False
        )
        self.registry = ToolRegistry()
        self.registry.register(DummyTool())
        self.agent = AgentCore(config=self.config, registry=self.registry)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_system_prompt_contains_all_core_directives(self):
        """Verifica que el System Prompt contenga las 5 directivas maestras explícitas."""
        prompt = self.agent._build_system_prompt()
        self.assertIn("DIRECTIVAS MAESTRAS DE ARQUITECTURA Y EJECUCIÓN", prompt)
        self.assertIn("AUTONOMÍA ESTRICTA DE EJECUCIÓN (CERO PAUSAS INTERMEDIAS)", prompt)
        self.assertIn("AISLAMIENTO DE HERRAMIENTAS (TOOL CALLING INTEGRITY)", prompt)
        self.assertIn("PRESERVACIÓN DE CONTEXTO Y PREVENCIÓN DE REGRESIÓN DE CÓDIGO", prompt)
        self.assertIn("HIGIENE DE DEPENDENCIAS DEL ENTORNO (STDLIB FIRST)", prompt)
        self.assertIn("ESTÁNDARES DE INGENIERÍA SENIOR (CONCURRENCIA ROBUSTA Y TESTING SIMULADO)", prompt)

    def test_02_planner_prompt_enforces_autonomy_and_stdlib_hygiene(self):
        """Verifica que el prompt del DAGPlanner enfatice autonomía e higiene de dependencias."""
        planner = DAGPlanner(llm_client=MagicMock())
        captured_messages = []

        def mock_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return LLMResponse(content='[{"id": 1, "title": "T1", "description": "D1", "expected_verification": "ok", "dependencies": []}]')

        planner.llm.chat = MagicMock(side_effect=mock_chat)
        planner.create_plan("Crear microservicio")

        sys_msg = next((m["content"] for m in captured_messages if m["role"] == "system"), "")
        self.assertIn("Autonomía Estricta", sys_msg)
        self.assertIn("Higiene de Dependencias (Stdlib First)", sys_msg)
        self.assertIn("pip install", sys_msg)

    def test_03_verifier_rejects_pip_install_of_stdlib_modules(self):
        """Verifica que ActionVerifier rechace intentos de instalar paquetes estándar con pip."""
        verifier = ActionVerifier(workspace_dir=self.workspace_dir)

        # Intento de pip install asyncio
        res = verifier.verify_action(
            tool_name="execute_command",
            arguments={"command": "pip install asyncio"},
            result=ToolResult(success=True, output="Collecting asyncio...")
        )
        self.assertFalse(res.passed)
        self.assertIn("biblioteca estándar de Python", res.reason)
        self.assertIn("asyncio", res.reason)

        # Intento de pip install threading
        res_thread = verifier.verify_action(
            tool_name="execute_command",
            arguments={"command": "pip install threading"},
            result=ToolResult(success=True, output="Collecting threading...")
        )
        self.assertFalse(res_thread.passed)
        self.assertIn("biblioteca estándar de Python", res_thread.reason)

        # Comando normal no debe ser rechazado
        res_ok = verifier.verify_action(
            tool_name="execute_command",
            arguments={"command": "pip install requests"},
            result=ToolResult(success=True, output="Successfully installed requests")
        )
        self.assertTrue(res_ok.passed)

    def test_04_sanitize_final_answer_removes_raw_tool_json_and_internal_questions(self):
        """Verifica que _sanitize_final_answer limpie esquemas JSON de llamadas y preguntas intermedias."""
        raw_output = (
            "¿Qué necesito hacer ahora? Voy a ejecutar la herramienta.\n"
            "```json\n"
            '{"name": "execute_python", "arguments": {"code": "print(1)"}}\n'
            "```\n"
            "El resultado fue exitoso."
        )
        cleaned = self.agent._sanitize_final_answer(raw_output)
        self.assertNotIn('{"name": "execute_python"', cleaned)
        self.assertNotIn("¿Qué necesito hacer ahora?", cleaned)
        self.assertIn("El resultado fue exitoso.", cleaned)

    def test_05_strict_autonomy_nudges_when_dag_is_incomplete(self):
        """Verifica que el agente no pause prematuramente si quedan subtareas pendientes en el DAG."""
        call_count = 0

        def mock_chat(*args, **kwargs):
            nonlocal call_count
            if not kwargs.get("tools"):
                return LLMResponse(content='[{"id": 1, "title": "Paso 1", "description": "D1", "expected_verification": "ok", "dependencies": []}, {"id": 2, "title": "Paso 2", "description": "D2", "expected_verification": "ok", "dependencies": [1]}]')
            call_count += 1
            if call_count == 1:
                return LLMResponse(content="", tool_calls=[{"id": "c1", "name": "execute_command", "arguments": {"command": "echo 1"}}])
            elif call_count == 2:
                return LLMResponse(content="Paso 1 listo. ¿Qué necesito hacer ahora?", tool_calls=[])
            elif call_count == 3:
                return LLMResponse(content="", tool_calls=[{"id": "c2", "name": "execute_command", "arguments": {"command": "echo 2"}}])
            else:
                return LLMResponse(content="Ambas tareas completadas.", tool_calls=[])

        self.agent.llm.chat = MagicMock(side_effect=mock_chat)
        res = self.agent.run_task("Ejecutar flujo de dos pasos")

        self.assertGreaterEqual(call_count, 3)
        self.assertIn("Ambas tareas completadas", res)

    def test_06_procedural_memory_persists_core_directives_and_dependency_hygiene(self):
        """Verifica que la base de datos SQLite y memoria procedimental contengan las directivas maestras."""
        memory = HierarchicalMemory(memory_dir=self.memory_dir)

        solutions = memory.search_solutions("autonomia ejecucion herramientas")
        self.assertTrue(any(s["category"] == "core_agent_directives" for s in solutions))

        dep_solutions = memory.search_solutions("pip install dependencias paquete")
        self.assertTrue(any(s["category"] == "dependency_hygiene" for s in dep_solutions))

        lessons = memory.get_all_lessons()
        self.assertTrue(any("Directivas Maestras" in l["category"] for l in lessons))


if __name__ == "__main__":
    unittest.main()
