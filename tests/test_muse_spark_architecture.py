"""
Suite de Pruebas Unitarias para la Arquitectura Muse Spark en JEV.
Verifica:
1. ToolRegistry: Registro de funciones Python y comandos shell, generación de schemas.
2. ExecutionEngine: Ejecución de subprocesos, funciones nativas, captura de stdout/stderr y sandbox.
3. MuseStateManager: Persistencia en SQLite, trazabilidad de turnos, estados de pasos e hipótesis.
4. AgentLoop: Parseo de canal de intención, auto-corrección ante fallos y finalización de tareas.
"""
import unittest
import tempfile
import sqlite3
import json
from pathlib import Path
from unittest.mock import MagicMock

from jev.core.muse import (
    ToolRegistry,
    ExecutionEngine,
    ExecutionResult,
    MuseStateManager,
    PlanStep,
    StepStatus,
    TaskStatus,
    TurnRecord,
    AgentLoop,
    LoopResult,
    MUSE_SPARK_SYSTEM_PROMPT
)
from jev.core.llm_client import LLMResponse


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_python_function(self):
        def sum_numbers(a: int, b: int) -> int:
            """Suma dos enteros."""
            return a + b

        self.registry.register_function("sum_two", sum_numbers)
        self.assertTrue(self.registry.has_tool("sum_two"))
        
        tool = self.registry.get_tool("sum_two")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "sum_two")
        self.assertIn("Suma dos enteros", tool.description)
        self.assertEqual(tool.parameters["type"], "object")
        self.assertIn("a", tool.parameters["properties"])
        self.assertIn("b", tool.parameters["properties"])

    def test_register_shell_command(self):
        self.registry.register_shell_command("my_shell", description="Ejecuta comandos shell.")
        self.assertTrue(self.registry.has_tool("my_shell"))
        tool = self.registry.get_tool("my_shell")
        self.assertTrue(tool.is_shell_command)
        self.assertIn("command", tool.parameters["properties"])

    def test_get_schema_text_formatting(self):
        self.registry.register_function("test_fn", lambda msg: msg, description="Función de prueba.")
        schema_text = self.registry.get_schema_text()
        self.assertIn("test_fn", schema_text)
        self.assertIn("Función de prueba", schema_text)


class TestExecutionEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.registry = ToolRegistry()
        self.engine = ExecutionEngine(registry=self.registry, workspace_dir=self.workspace)

    def test_execute_python_function(self):
        def multiply(x: int, y: int) -> int:
            return x * y

        self.registry.register_function("mult", multiply)
        res = self.engine.execute_action("mult", {"x": 6, "y": 7})
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "42")
        self.assertGreaterEqual(res.duration, 0.0)

    def test_execute_shell_subprocess(self):
        self.registry.register_shell_command("shell")
        res = self.engine.execute_action("shell", {"command": "echo 'MUSE_SPARK_OK'"})
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertIn("MUSE_SPARK_OK", res.output)

    def test_sandbox_blocks_destructive_command(self):
        self.registry.register_shell_command("shell")
        # El comando destructivo debe ser bloqueado por ExecutionSandbox
        res = self.engine.execute_action("shell", {"command": "format C:"})
        self.assertFalse(res.success)
        self.assertIn("Sandbox", res.error)

    def test_missing_tool_returns_error(self):
        res = self.engine.execute_action("herramienta_fantasma", {})
        self.assertFalse(res.success)
        self.assertEqual(res.exit_code, 127)
        self.assertIn("Herramienta no encontrada", res.error)


class TestMuseStateManager(unittest.TestCase):

    def setUp(self):
        self.state_mgr = MuseStateManager(db_path=Path(":memory:"))

    def tearDown(self):
        self.state_mgr.close()

    def test_create_and_query_task(self):
        steps = [
            PlanStep(step_index=1, title="Paso Uno", description="Desc Uno"),
            PlanStep(step_index=2, title="Paso Dos", description="Desc Dos")
        ]
        task_id = self.state_mgr.create_task("Meta de prueba", steps)
        self.assertTrue(bool(task_id))

        retrieved_steps = self.state_mgr.get_plan_steps(task_id)
        self.assertEqual(len(retrieved_steps), 2)
        self.assertEqual(retrieved_steps[0].title, "Paso Uno")
        self.assertEqual(retrieved_steps[0].status, StepStatus.PENDING)

    def test_state_transitions_and_hypothesis(self):
        steps = [PlanStep(step_index=1, title="Paso Uno", description="Desc Uno")]
        task_id = self.state_mgr.create_task("Meta", steps)

        # Iniciar paso
        self.state_mgr.mark_step_in_progress(task_id, 1)
        active = self.state_mgr.get_active_step(task_id)
        self.assertEqual(active.status, StepStatus.IN_PROGRESS)

        # Registrar fallo con hipótesis
        retries = self.state_mgr.record_step_failure(
            task_id, 1, error="FileNotFound", hypothesis="El archivo debe ser creado primero"
        )
        self.assertEqual(retries, 1)
        active_after = self.state_mgr.get_active_step(task_id)
        self.assertEqual(active_after.hypothesis, "El archivo debe ser creado primero")

        # Completar paso
        self.state_mgr.mark_step_completed(task_id, 1, "Archivo generado con éxito.")
        active_final = self.state_mgr.get_active_step(task_id)
        self.assertIsNone(active_final)  # No quedan pasos pendientes

    def test_turn_history_persistence(self):
        steps = [PlanStep(step_index=1, title="Paso Uno", description="Desc")]
        task_id = self.state_mgr.create_task("Meta", steps)

        record = TurnRecord(
            turn_index=1,
            step_index=1,
            thought="Pensamiento de prueba",
            intent="Intención de prueba",
            action="mi_accion",
            params={"k": "v"},
            success=True,
            output="Salida de prueba"
        )
        self.state_mgr.record_turn(task_id, record)

        recent = self.state_mgr.get_recent_turns(task_id, limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].thought, "Pensamiento de prueba")
        self.assertEqual(recent[0].intent, "Intención de prueba")
        self.assertEqual(recent[0].action, "mi_accion")
        self.assertEqual(recent[0].params, {"k": "v"})


class TestAgentLoop(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.registry = ToolRegistry()
        self.engine = ExecutionEngine(registry=self.registry, workspace_dir=self.workspace)
        self.state_mgr = MuseStateManager(db_path=Path(":memory:"))

    def tearDown(self):
        self.state_mgr.close()

    def test_parse_intent_payload_json_block(self):
        loop = AgentLoop(registry=self.registry, engine=self.engine, state_manager=self.state_mgr)
        raw = """Aquí está mi razonamiento:
```json
{
  "thought": "Debo listar los archivos",
  "intent": "Voy a inspeccionar el directorio",
  "action": "list_files",
  "params": {"dir": "workspace"}
}
```
"""
        parsed = loop._parse_intent_payload(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["thought"], "Debo listar los archivos")
        self.assertEqual(parsed["intent"], "Voy a inspeccionar el directorio")
        self.assertEqual(parsed["action"], "list_files")
        self.assertEqual(parsed["params"], {"dir": "workspace"})

    def test_loop_executes_plan_and_finishes(self):
        # Función de prueba
        self.registry.register_function("echo_tool", lambda msg: f"Echo: {msg}")

        # Simular respuestas del modelo
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [
            # Turno 1: Ejecutar herramienta
            LLMResponse(content=json.dumps({
                "thought": "Voy a invocar la herramienta de echo",
                "intent": "Llamando a echo_tool",
                "action": "echo_tool",
                "params": {"msg": "Hola Muse"}
            })),
            # Turno 2: Completar paso 1
            LLMResponse(content=json.dumps({
                "thought": "Echo funcionó correctamente",
                "intent": "Completando paso 1",
                "action": "complete_step",
                "params": {"summary": "Echo verificado"}
            })),
            # Turno 3: Finalizar tarea global
            LLMResponse(content=json.dumps({
                "thought": "Plan terminado",
                "intent": "Cerrando la tarea",
                "action": "finish",
                "params": {"final_result": "Meta cumplida con éxito."}
            }))
        ]

        loop = AgentLoop(
            registry=self.registry,
            engine=self.engine,
            state_manager=self.state_mgr,
            llm_client=mock_llm,
            max_iterations=10
        )

        preplanned = [
            {"title": "Paso Echo", "description": "Verificar echo"},
            {"title": "Paso Final", "description": "Cierre de meta"}
        ]
        result = loop.run("Comprobar echo", preplanned_steps=preplanned)

        self.assertTrue(result.success)
        self.assertEqual(result.steps_completed, 2)
        self.assertEqual(result.total_steps, 2)
        self.assertEqual(result.total_turns, 3)
        self.assertIn("Meta cumplida", result.final_output)


if __name__ == "__main__":
    unittest.main()
