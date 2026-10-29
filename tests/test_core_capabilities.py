"""
Pruebas exhaustivas para las capacidades de producción de JEV:
1. Protocolo de verificación y bucle de reflexión (ActionVerifier).
2. Memoria jerárquica (SQLite long-term + short-term deduplication).
3. Sandbox de ejecución y terminal segura.
4. Planificador DAG con límite de 3 reintentos y pivoteo.
5. Checkpoints de estado persistentes.
6. Validación estricta de esquemas de herramientas.
7. Botón de parada de emergencia.
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from jev.core.verifier import ActionVerifier, VerificationResult
from jev.core.sandbox import ExecutionSandbox
from jev.core.planner import TaskPlan, SubTask
from jev.core.checkpoints import CheckpointManager
from jev.core.memory import HierarchicalMemory
from jev.tools.base import ToolRegistry, ToolResult, BaseTool
from jev.tools.filesystem import WriteFileTool, ReadFileTool
from jev.tools.code_runner import ShellCommandTool, PythonRunnerTool
from jev.core.agent import AgentCore
from jev.config import AgentConfig


class TestCoreCapabilities(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True)
        self.memory_dir = self.temp_dir / "memory"
        self.memory_dir.mkdir(parents=True)
        self.checkpoints_dir = self.temp_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sandbox_blocks_dangerous_commands(self):
        """Verifica que el Sandbox bloquee comandos destructivos en Windows."""
        dangerous_cmds = [
            "format D: /fs:NTFS",
            "diskpart /s script.txt",
            "rmdir /s /q C:\\",
            "reg delete HKLM\\Software",
            "shutdown /s /f /t 0"
        ]
        for cmd in dangerous_cmds:
            safe, err = ExecutionSandbox.validate_command(cmd)
            self.assertFalse(safe, f"El comando '{cmd}' debió ser bloqueado.")
            self.assertIn("Sandbox", err)

        safe_cmd = "dir"
        safe, err = ExecutionSandbox.validate_command(safe_cmd)
        self.assertTrue(safe)
        self.assertIsNone(err)

    def test_sandbox_protects_system_directories(self):
        """Verifica que el Sandbox impida modificar directorios críticos del sistema."""
        protected_paths = [
            Path("C:/Windows/System32/critical.dll"),
            Path("C:/Program Files/test.txt")
        ]
        for p in protected_paths:
            safe, err = ExecutionSandbox.validate_path_safety(p, allow_read_only=False)
            self.assertFalse(safe)
            self.assertIn("Acceso restringido", err)

    def test_action_verifier_checks_files_and_syntax(self):
        """Verifica que ActionVerifier detecte archivos vacíos y errores de sintaxis Python."""
        verifier = ActionVerifier()

        # 1. Archivo inexistente
        res = ToolResult(success=True, output="Hecho")
        v = verifier.verify_action("write_file", {"path": str(self.workspace_dir / "inexistente.txt")}, res)
        self.assertFalse(v.passed)

        # 2. Archivo vacío (0 bytes)
        empty_file = self.workspace_dir / "vacio.txt"
        empty_file.write_text("", encoding="utf-8")
        v = verifier.verify_action("write_file", {"path": str(empty_file)}, res)
        self.assertFalse(v.passed)
        self.assertIn("vacío", v.reason)

        # 3. Archivo Python con error de sintaxis
        bad_py = self.workspace_dir / "bad_syntax.py"
        bad_py.write_text("def error_func(:\n    print('error')", encoding="utf-8")
        v = verifier.verify_action("write_file", {"path": str(bad_py)}, res)
        self.assertFalse(v.passed)
        self.assertIn("sintaxis", v.reason.lower())

        # 4. Archivo Python válido
        good_py = self.workspace_dir / "good_syntax.py"
        good_py.write_text("def ok():\n    return 42\n", encoding="utf-8")
        v = verifier.verify_action("write_file", {"path": str(good_py)}, res)
        self.assertTrue(v.passed)

    def test_action_verifier_checks_python_execution(self):
        """Verifica que ActionVerifier detecte fallos de ejecución en Python."""
        verifier = ActionVerifier()

        # Fallo con exit_code != 0
        failed_res = ToolResult(
            success=False,
            output="Error",
            error="ZeroDivisionError",
            data={"exit_code": 1, "stderr": "ZeroDivisionError: division by zero"}
        )
        v = verifier.verify_action("execute_python", {"code": "1/0"}, failed_res)
        self.assertFalse(v.passed)

        # Éxito con exit_code == 0
        success_res = ToolResult(
            success=True,
            output="42",
            data={"exit_code": 0, "stderr": ""}
        )
        v = verifier.verify_action("execute_python", {"code": "print(42)"}, success_res)
        self.assertTrue(v.passed)

    def test_hierarchical_memory_sqlite_and_deduplication(self):
        """Verifica la persistencia en SQLite de memoria procedimental y deduplicación en memoria de trabajo."""
        mem = HierarchicalMemory(self.memory_dir)

        # 1. Almacenar solución procedimental
        mem.save_solution(
            category="web_scraping",
            trigger_keywords="crawl extraer html trafilatura",
            problem_description="Error 403 al extraer con user-agent genérico",
            solution_summary="Usar trafilatura con header de navegador personalizado",
            working_snippet="import trafilatura\nhtml = trafilatura.fetch_url(url)"
        )

        # Buscar solución
        results = mem.search_solutions("como extraer html")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "web_scraping")
        self.assertIn("trafilatura", results[0]["working_snippet"])

        # 2. Comprobar deduplicación de memoria de trabajo (Short-term)
        session = "session_test_123"
        tool_args = {"path": "test.txt", "content": "hola"}
        self.assertFalse(mem.is_step_duplicated(session, "write_file", tool_args))

        mem.record_step(session, 1, "write_file", tool_args, success=True)
        self.assertTrue(mem.is_step_duplicated(session, "write_file", tool_args))
        # Argumentos distintos no deben ser duplicados
        self.assertFalse(mem.is_step_duplicated(session, "write_file", {"path": "otro.txt"}))

    def test_dag_planner_pivots_after_3_retries(self):
        """Verifica que el plan DAG aplique el límite estricto de 3 reintentos antes de pivotar."""
        t1 = SubTask(
            id=1,
            title="Subtarea compleja",
            description="Intentar llamada",
            expected_verification="Código 0",
            max_retries=3
        )
        t2 = SubTask(
            id=2,
            title="Subtarea secundaria",
            description="Plan alternativo",
            expected_verification="Resultado válido",
            dependencies=[]
        )
        plan = TaskPlan(goal="Meta de prueba", tasks=[t1, t2])

        # Intento 1 fallido
        pivoted, _ = plan.record_failure_and_check_pivot(1, "Error timeout")
        self.assertFalse(pivoted)
        self.assertEqual(t1.retries, 1)

        # Intento 2 fallido
        pivoted, _ = plan.record_failure_and_check_pivot(1, "Error timeout")
        self.assertFalse(pivoted)
        self.assertEqual(t1.retries, 2)

        # Intento 3 fallido -> DEBE PIVOTAR
        pivoted, _ = plan.record_failure_and_check_pivot(1, "Error definitivo")
        self.assertTrue(pivoted)
        self.assertEqual(t1.status, "pivoted")

        # El siguiente disponible debe ser la subtarea 2
        next_t = plan.get_next_available_task()
        self.assertIsNotNone(next_t)
        self.assertEqual(next_t.id, 2)

    def test_checkpoint_manager_save_and_load(self):
        """Verifica la persistencia y recuperación de checkpoints en disco."""
        mgr = CheckpointManager(self.checkpoints_dir)
        task_id = "test_task_999"
        plan_dict = {"goal": "Test goal", "tasks": []}

        saved_path = mgr.save_checkpoint(
            task_id=task_id,
            goal="Test goal",
            plan_dict=plan_dict,
            completed_step_count=3,
            messages=[{"role": "user", "content": "hi"}]
        )
        self.assertTrue(saved_path.exists())

        loaded = mgr.load_checkpoint(task_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["completed_steps"], 3)
        self.assertEqual(loaded["goal"], "Test goal")

        mgr.clear_checkpoint(task_id)
        self.assertIsNone(mgr.load_checkpoint(task_id))

    def test_structured_tool_schema_validation(self):
        """Verifica que llamadas con parámetros faltantes o tipos incorrectos sean rechazadas antes de ejecutarse."""
        registry = ToolRegistry()
        write_tool = WriteFileTool()
        registry.register(write_tool)

        # Llamada inválida: falta el parámetro requerido 'content'
        res = registry.execute_call("write_file", {"path": "test.txt"})
        self.assertFalse(res.success)
        self.assertIn("content", res.error)
        self.assertIn("Faltan los parámetros requeridos", res.error)

    def test_emergency_stop_halts_agent(self):
        """Verifica que llamar a stop() interrumpa inmediatamente la ejecución."""
        config = AgentConfig(max_iterations=10, memory_dir=self.memory_dir)
        agent = AgentCore(config=config, memory=HierarchicalMemory(self.memory_dir))
        agent.stop()
        res = agent.run_task("Cualquier tarea")
        self.assertIn("PARADA DE EMERGENCIA", res)

    def test_system_environment_tool(self):
        """Verifica que SystemEnvironmentTool reporte correctamente el SO, hardware y binarios."""
        from jev.tools.system_info import SystemEnvironmentTool
        tool = SystemEnvironmentTool(workspace_dir=self.workspace_dir)
        res = tool.execute()
        self.assertTrue(res.success)
        self.assertIn("INFORME DE ENTORNO", res.output)
        self.assertIn("python", res.output.lower())
        self.assertIn("git", res.output.lower())
        self.assertIn("ram_gb", res.data)

    def test_package_manager_tool_input_validation(self):
        """Verifica que PackageManagerTool rechace entradas no válidas y ejecute en el venv."""
        from jev.tools.code_runner import PackageManagerTool
        tool = PackageManagerTool()
        # Rechazo de inyección
        res = tool.execute("pandas; rm -rf /")
        self.assertFalse(res.success)
        self.assertIn("no válido", res.error.lower())

    def test_context_compression(self):
        """Verifica que AgentCore condense historiales de conversación largos en un resumen sintetizado."""
        config = AgentConfig(max_iterations=5, memory_dir=self.memory_dir)
        agent = AgentCore(config=config, memory=HierarchicalMemory(self.memory_dir))
        
        # Simular 18 mensajes en el historial
        agent.messages = [
            {"role": "system", "content": "System prompt maestro"},
            {"role": "user", "content": "Meta original"}
        ]
        for i in range(16):
            agent.messages.append({
                "role": "tool" if i % 2 == 0 else "assistant",
                "name": f"tool_{i}",
                "content": f"Salida de paso {i} con datos extensos..."
            })
        
        self.assertEqual(len(agent.messages), 18)
        agent._compress_messages_if_needed()
        # Debe haber comprimido los mensajes intermedios manteniendo cabeza y cola
        self.assertLess(len(agent.messages), 18)
        self.assertEqual(agent.messages[0]["content"], "System prompt maestro")
        self.assertEqual(agent.messages[1]["content"], "Meta original")
        self.assertIn("RESUMEN SINTETIZADO", agent.messages[2]["content"])


if __name__ == "__main__":
    unittest.main()
