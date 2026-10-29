"""
Pruebas de integración del motor MMAE (Macro-Micro Agent Engine).
Verifica:
  1. LiteralBypass: apantallamiento y restauración exacta de rutas y hashes.
  2. TaskPlanner: parseo y seguimiento de tareas desde esqueletos macro.
  3. OutputEvaluator: validación sintáctica mediante AST.
  4. ReflectionLoop: reintentos y tolerancia a fallos.
  5. MMAEAutonomousAgent: ciclo completo y persistencia en disco.
"""
import unittest
from pathlib import Path

from utils.bypass import LiteralBypass
from core.planner import TaskPlanner
from core.evaluator import OutputEvaluator
from core.memory import ExecutionMemory
from core.reflection_loop import ReflectionLoop
from core.agent import MMAEAutonomousAgent
from config import AgentConfig


class TestMMAEIntegration(unittest.TestCase):
    def test_literal_bypass_shield_and_restore(self):
        bypass = LiteralBypass()
        raw_text = "Revisar ruta C:/Users/test/project/file.py y el commit a1b2c3d4e5f6."
        shielded = bypass.extract_and_shield(raw_text)

        self.assertNotIn("C:/Users/test/project/file.py", shielded["clean_text"])
        self.assertIn("__LITERAL_TOKEN_", shielded["clean_text"])
        self.assertEqual(len(shielded["literals"]), 2)

        # Restauración
        restored = bypass.restore(shielded["clean_text"], shielded["literals"])
        self.assertEqual(restored, raw_text)

    def test_task_planner_parsing(self):
        planner = TaskPlanner()
        skeleton = (
            "1. Inspeccionar arquitectura local\n"
            "2. Ejecutar pruebas unitarias\n"
            "3. Compilar reporte"
        )
        tasks = planner.parse_tasks_from_skeleton(skeleton)
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0]["description"], "Inspeccionar arquitectura local")
        self.assertFalse(planner.is_finished())

        # Completar pasos
        t1 = planner.get_next_task()
        self.assertEqual(t1["id"], 1)
        planner.complete_current_task(success=True)

        t2 = planner.get_next_task()
        self.assertEqual(t2["id"], 2)
        planner.complete_current_task(success=True)

        t3 = planner.get_next_task()
        self.assertEqual(t3["id"], 3)
        planner.complete_current_task(success=True)

        self.assertTrue(planner.is_finished())

    def test_output_evaluator_ast(self):
        valid_code = "def saludo(nombre: str) -> str:\n    return f'Hola {nombre}'"
        res_valid = OutputEvaluator.validate_python_code(valid_code)
        self.assertTrue(res_valid["valid"])

        invalid_code = "def roto(:\n    return 42"
        res_invalid = OutputEvaluator.validate_python_code(invalid_code)
        self.assertFalse(res_invalid["valid"])
        self.assertIn("Error de sintaxis", res_invalid["error"])

    def test_reflection_loop_retry(self):
        mem = ExecutionMemory(max_history=5)
        loop = ReflectionLoop(memory=mem, max_retries=3)

        attempts = 0
        def flappy_step():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                return {"success": False, "error": "Fallo simulado"}
            return {"success": True, "stdout": "Operación exitosa"}

        result = loop.execute_with_retry("test_action", flappy_step)
        self.assertTrue(result["success"])
        self.assertEqual(attempts, 2)
        self.assertEqual(len(mem.history), 2)

    def test_mmae_agent_full_run(self):
        cfg = AgentConfig()
        agent = MMAEAutonomousAgent(cfg)
        res = agent.run("Auditoría de entorno de prueba")

        self.assertIn("tasks", res)
        self.assertGreaterEqual(len(res["tasks"]), 1)
        self.assertIn("results", res)
        self.assertTrue(Path(agent.persistence.storage_path).exists())


if __name__ == "__main__":
    unittest.main()
