"""
Suite de Pruebas Unitarias para las Nuevas Adiciones de MMAE-Agent:
1. Memoria Persistente a Largo Plazo (Mem0 Layer).
2. Capa de Control y Ejecución de Sistema Operativo (CLI Anything Layer).
3. Salvaguardas de Ejecución y Presupuesto (Guardrails: Circuit Breaker, Flapping Detector, Budget Guard).
"""
import unittest
import tempfile
import shutil
import time
from pathlib import Path

# 1. Imports de Mem0
from core.memory.user_memory import UserPersistentMemory, UserMemoryCategory
from core.memory.mem0_bridge import Mem0Bridge
from jev.tools.mem0_tool import Mem0MemoryTool

# 2. Imports de CLI Anything
from core.tools.cli_anything import (
    CLIAnythingRunner,
    CLIExecutionResult,
    CLICommandValidator
)
from jev.tools.cli_anything import CLIAnythingTool

# 3. Imports de Guardrails
from core.guardrails import (
    CircuitBreakerState,
    ToolCircuitBreaker,
    ToolFlappingDetector,
    ExecutionBudgetGuard,
    GuardrailManager,
    GuardrailDecision
)

# 4. Imports de Tools
from jev.tools import build_default_registry


class TestMMAENewArchitecturalLayers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mmae_test_layers_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. PRUEBAS DE MEMORIA A LARGO PLAZO (MEM0 LAYER)
    # =========================================================================
    def test_mem0_persistent_categories_and_recall(self):
        """Verifica el almacenamiento y recall de preferencias, rutas y errores."""
        bridge = Mem0Bridge(db_dir=self.temp_dir)

        # 1. Preferencia
        res_pref = bridge.remember_preference("ui_mode", "modo_oscuro_conciso")
        self.assertIn(res_pref["action"], ("created", "updated"))

        # 2. Ruta habitual
        res_path = bridge.remember_path("c:/proyectos/mmae-agent/src", "Directorio fuente principal")
        self.assertIn(res_path["action"], ("created", "updated"))

        # 3. Resolución de error previo
        res_err = bridge.remember_error_resolution(
            "ModelNotFound: gemini-2.5-pro 404",
            "Usar modelo gemini-3.5-flash-lite en config.py"
        )
        self.assertIn(res_err["action"], ("created", "updated"))

        # 4. Proactive Recall para una tarea
        recalled = bridge.recall_for_task("Arreglar error 404 de gemini en proyectos")
        self.assertTrue(len(recalled["error_resolutions"]) > 0)
        self.assertTrue(len(recalled["habitual_paths"]) > 0)

        # 5. Generación de contexto para prompt
        ctx = bridge.build_prompt_context("Necesito trabajar en proyectos con gemini")
        self.assertIn("RUTAS HABITUALES", ctx)
        self.assertIn("RESOLUCIONES DE ERRORES", ctx)

    def test_mem0_automated_session_learnings(self):
        """Verifica la extracción automática post-tarea de rutas y errores subsanados."""
        mem = UserPersistentMemory(db_path=self.temp_dir / "user.db")
        written = [("workspace/reporte_final.py", "print('ok')")]
        fixed = [{"error": "PlaywrightChromiumMissing", "resolution": "channel='msedge'"}]

        results = mem.extract_session_learnings(
            user_goal="Generar reporte y automatizar navegador",
            written_files=written,
            errors_fixed=fixed
        )
        self.assertEqual(len(results), 2)

        # Comprobar que quedaron persistidos
        all_mems = mem.get_all()
        categories = {m["category"] for m in all_mems}
        self.assertIn(UserMemoryCategory.HABITUAL_PATH.value, categories)
        self.assertIn(UserMemoryCategory.ERROR_RESOLUTION.value, categories)

    def test_mem0_agent_tool(self):
        """Verifica la herramienta manage_user_memory expuesta al LLM."""
        bridge = Mem0Bridge(db_dir=self.temp_dir)
        tool = Mem0MemoryTool(mem0_bridge=bridge)

        # Remember
        r1 = tool.execute(action="remember", key="idioma", value="español estricto", category="preference")
        self.assertTrue(r1.success)

        # Remember path
        r2 = tool.execute(action="remember_path", value="c:/data/models", key="modelos locales")
        self.assertTrue(r2.success)

        # Recall
        r3 = tool.execute(action="recall", query="idioma")
        self.assertTrue(r3.success)
        self.assertIn("español", r3.output)

    # =========================================================================
    # 2. PRUEBAS DE CAPA DE CONTROL Y EJECUCIÓN (CLI ANYTHING LAYER)
    # =========================================================================
    def test_cli_anything_execution_and_schema(self):
        """Verifica ejecución estándar de CLI, captura de métricas y JSON normalizado."""
        runner = CLIAnythingRunner(working_dir=self.temp_dir)
        # Ejecutar python nativo con sys.executable
        res: CLIExecutionResult = runner.execute("python", ["-c", "print('MMAE_CLI_TEST_OK')"])
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertIn("MMAE_CLI_TEST_OK", res.stdout)
        self.assertGreater(res.duration_ms, 0)
        self.assertFalse(res.timed_out)

        # Verificar serialización JSON
        json_str = res.to_json()
        self.assertIn("MMAE_CLI_TEST_OK", json_str)
        self.assertIn("duration_ms", json_str)

    def test_cli_anything_security_injection_prevention(self):
        """Verifica que patrones de inyección shell peligrosos sean rechazados por el validador."""
        runner = CLIAnythingRunner(working_dir=self.temp_dir)
        res = runner.execute("python", ["-c", "print('test'); rm -rf /; format c:"])
        self.assertFalse(res.success)
        self.assertEqual(res.exit_code, -1)
        self.assertIn("seguridad", res.stderr.lower())

    def test_cli_anything_agent_tool(self):
        """Verifica que CLIAnythingTool responde con éxito y formato amigable."""
        runner = CLIAnythingRunner(working_dir=self.temp_dir)
        tool = CLIAnythingTool(runner=runner)
        res = tool.execute(executable="python", arguments=["-c", "print('CLI_TOOL_SUCCESS')"])
        self.assertTrue(res.success)
        self.assertIn("CLI_TOOL_SUCCESS", res.output)
        self.assertIn("Duración:", res.output)

    # =========================================================================
    # 3. PRUEBAS DE SALVAGUARDAS Y PRESUPUESTO (GUARDRAILS)
    # =========================================================================
    def test_circuit_breaker_trips_and_recovers(self):
        """Verifica que 3 fallos consecutivos abren el Circuit Breaker."""
        cb = ToolCircuitBreaker(failure_threshold=3, recovery_cooldown_seconds=0.5)

        # Inicialmente cerrado
        ok, reason, _ = cb.can_execute("broken_tool")
        self.assertTrue(ok)

        # 3 fallos consecutivos
        cb.record_failure("broken_tool", "Error de conexión 1")
        cb.record_failure("broken_tool", "Error de conexión 2")
        cb.record_failure("broken_tool", "Error de conexión 3")

        # Ahora debe estar OPEN y bloquear
        ok, reason, action = cb.can_execute("broken_tool")
        self.assertFalse(ok)
        self.assertIn("CIRCUIT BREAKER [OPEN]", reason)
        self.assertIsNotNone(action)

        # Esperar cooldown y verificar transición a HALF_OPEN
        time.sleep(0.6)
        ok_half, reason_half, _ = cb.can_execute("broken_tool")
        self.assertTrue(ok_half)
        self.assertIn("HALF_OPEN", reason_half)

        # Si la llamada de prueba tiene éxito, regresa a CLOSED
        cb.record_success("broken_tool")
        ok_closed, _, _ = cb.can_execute("broken_tool")
        self.assertTrue(ok_closed)

    def test_flapping_detector_trips_on_ping_pong(self):
        """Verifica detección de flapping alternante A -> B -> A -> B."""
        detector = ToolFlappingDetector(history_window=8)
        now = time.time()

        # Secuencia: toolA -> toolB -> toolA
        detector.record_call("read_file", {"path": "a.txt"}, success=True, timestamp=now)
        detector.record_call("write_file", {"path": "a.txt"}, success=True, timestamp=now + 1)
        detector.record_call("read_file", {"path": "a.txt"}, success=True, timestamp=now + 2)

        # Próxima llamada candidata: write_file -> Completa patrón de flapping
        is_flap, reason, fix = detector.check_flapping("write_file")
        self.assertTrue(is_flap)
        self.assertIn("Flapping detectado", reason)
        self.assertIn("read_file", reason)
        self.assertIn("write_file", reason)
        self.assertIsNotNone(fix)

    def test_budget_guard_limits(self):
        """Verifica límites presupuestarios por microtarea y global."""
        budget = ExecutionBudgetGuard(max_task_iterations=5, max_subtask_iterations=2)
        budget.start_task()

        # Microtarea 1: 2 iteraciones permitidas
        budget.increment_iteration(subtask_id="task_1")
        ok, _, _ = budget.check_budget(subtask_id="task_1")
        self.assertTrue(ok)

        budget.increment_iteration(subtask_id="task_1")
        # Al llegar al límite de la microtarea:
        ok_sub, reason, fix = budget.check_budget(subtask_id="task_1")
        self.assertFalse(ok_sub)
        self.assertIn("Microtarea [task_1] excedió su límite", reason)

    def test_guardrail_manager_integrated_decision(self):
        """Verifica el flujo integrado de GuardrailManager."""
        manager = GuardrailManager(
            failure_threshold=2,
            max_task_iterations=10,
            max_subtask_iterations=4
        )
        manager.start_task()

        # Invocación normal permitida
        d1 = manager.verify_invocation("search_web", {"query": "python"})
        self.assertTrue(d1.allowed)

        # Registrar 2 fallos consecutivos
        manager.record_result("search_web", {"query": "python"}, success=False, error="Rate limit")
        manager.record_result("search_web", {"query": "python"}, success=False, error="Rate limit")

        # La 3ra llamada debe ser interceptada por el circuit breaker
        d2 = manager.verify_invocation("search_web", {"query": "python"})
        self.assertFalse(d2.allowed)
        self.assertIn("CIRCUIT BREAKER", d2.reason)
        self.assertIn("ACCIÓN BLOQUEADA POR SALVAGUARDA", d2.to_feedback())

    # =========================================================================
    # 4. REGISTRO EN TOOLREGISTRY
    # =========================================================================
    def test_tools_registered_in_default_registry(self):
        """Verifica que las nuevas herramientas estén registradas en ToolRegistry."""
        registry, _ = build_default_registry()
        tool_names = [t.name for t in registry.list_tools()]
        self.assertIn("manage_user_memory", tool_names)
        self.assertIn("cli_execute_structured", tool_names)

        # Verificar esquemas OpenAI válidos
        mem_tool = registry.get("manage_user_memory")
        cli_tool = registry.get("cli_execute_structured")
        self.assertIsNotNone(mem_tool)
        self.assertIsNotNone(cli_tool)

        schema_mem = mem_tool.get_openai_schema()
        schema_cli = cli_tool.get_openai_schema()
        self.assertEqual(schema_mem["function"]["name"], "manage_user_memory")
        self.assertEqual(schema_cli["function"]["name"], "cli_execute_structured")


if __name__ == "__main__":
    unittest.main()
