"""
Pruebas unitarias para las capacidades asimiladas de OpenMythos:
- Motor cognitivo recurrente (RDT) y parada adaptativa (ACT)
- Enrutador de mezcla de expertos de agentes (MoAE)
- Herramienta de ejecución y evaluación neuronal (OpenMythosRunnerTool)
- Protocolo de verificación para estabilidad espectral LTI rho(A) < 1
"""
import unittest
from pathlib import Path

from jev.core.mythos_engine import MythosCognitiveEngine, MoAERouter, ACTState
from jev.tools.mythos_runner import OpenMythosRunnerTool
from jev.tools import build_default_registry
from jev.core.verifier import ActionVerifier
from jev.tools.base import ToolResult


class TestMythosCognitiveEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MythosCognitiveEngine(max_loops=4, act_threshold=0.85)

    def test_assess_complexity(self):
        # Meta simple
        score_simple = self.engine.assess_complexity("hola que tal")
        self.assertGreaterEqual(score_simple, 1)
        self.assertLessEqual(score_simple, 2)

        # Meta compleja multi-hop
        complex_goal = "analizar e implementar un algoritmo en github, refactorizar el codigo y optimizar para entrenar un modelo neural"
        score_complex = self.engine.assess_complexity(complex_goal)
        self.assertGreaterEqual(score_complex, 3)

    def test_recurrent_thinking_loop_and_act_halting(self):
        goal = "Desarrollar un optimizador de memoria en Python y verificar estabilidad"
        summary, act_state = self.engine.recurrent_thinking_loop(goal)

        self.assertIsInstance(summary, str)
        self.assertIn("Deliberación recurrente OpenMythos completada", summary)
        self.assertIsInstance(act_state, ACTState)
        self.assertGreaterEqual(act_state.current_loop, 1)
        self.assertLessEqual(act_state.current_loop, 4)
        self.assertGreater(act_state.cumulative_halt_prob, 0.5)
        # Verificar traza de razonamiento
        self.assertGreater(len(act_state.reasoning_trace), 0)
        first_step = act_state.reasoning_trace[0]
        self.assertIn("loop", first_step)
        self.assertIn("p_halt_step", first_step)


class TestMoAERouter(unittest.TestCase):
    def setUp(self):
        self.router = MoAERouter()
        self.registry, _ = build_default_registry()
        self.all_tools = self.registry.to_openai_tools()

    def test_shared_experts_always_present(self):
        tools, active_experts = self.router.route_tools("cualquier tarea basica", self.all_tools)
        tool_names = [t["function"]["name"] for t in tools]

        # Los expertos compartidos deben estar siempre presentes
        for shared in self.router.SHARED_EXPERT_TOOLS:
            self.assertIn(shared, tool_names)
        self.assertIn("Core Compartido (Shared Experts)", active_experts[0])

    def test_routing_by_domain_keywords(self):
        # 1. Búsqueda web
        tools_web, experts_web = self.router.route_tools("buscar en internet la documentacion de pytorch", self.all_tools)
        names_web = [t["function"]["name"] for t in tools_web]
        self.assertIn("search_web", names_web)
        self.assertIn("fetch_webpage", names_web)

        # 2. GitHub
        tools_gh, experts_gh = self.router.route_tools("clonar el repo de github para asimilar la libreria", self.all_tools)
        names_gh = [t["function"]["name"] for t in tools_gh]
        self.assertIn("search_github_repos", names_gh)
        self.assertIn("clone_github_repo", names_gh)
        self.assertIn("assimilate_github_library", names_gh)

        # 3. Pantalla / Computer Use
        tools_screen, experts_screen = self.router.route_tools("tomar un screenshot de la pantalla y hacer click en el boton", self.all_tools)
        names_screen = [t["function"]["name"] for t in tools_screen]
        self.assertIn("take_screenshot", names_screen)
        self.assertIn("mouse_click", names_screen)

        # 4. Neural OpenMythos
        tools_mythos, experts_mythos = self.router.route_tools("ejecutar un benchmark del modelo neural openmythos en cuda gpu", self.all_tools)
        names_mythos = [t["function"]["name"] for t in tools_mythos]
        self.assertIn("run_open_mythos", names_mythos)


class TestOpenMythosRunnerTool(unittest.TestCase):
    def setUp(self):
        self.tool = OpenMythosRunnerTool()
        self.verifier = ActionVerifier()

    def test_verify_spectral_stability(self):
        res = self.tool.execute(action="verify_stability", dim=64, n_loops=2, attn_type="mla")
        self.assertTrue(res.success, f"Fallo al verificar estabilidad: {res.error}")
        self.assertIn("ρ(A)", res.output)
        self.assertIn("CUMPLIDO", res.output)
        self.assertIsNotNone(res.data)
        self.assertLess(res.data["rho_A"], 1.0)

        # Verificador de acciones
        v_res = self.verifier.verify_action("run_open_mythos", {"action": "verify_stability"}, res)
        self.assertTrue(v_res.passed)

    def test_forward_test(self):
        res = self.tool.execute(action="forward_test", dim=64, n_loops=2, attn_type="gqa")
        self.assertTrue(res.success, f"Fallo en forward_test: {res.error}")
        self.assertIn("Pasada de Inferencia OpenMythos Exitosa", res.output)
        self.assertEqual(res.data["shape"][0], 1)
        self.assertEqual(res.data["shape"][1], 8)

    def test_benchmark(self):
        res = self.tool.execute(action="benchmark", dim=64, n_loops=2, attn_type="mla")
        self.assertTrue(res.success, f"Fallo en benchmark: {res.error}")
        self.assertIn("Benchmark Neuronal OpenMythos", res.output)
        self.assertIn("ms", res.output)
        self.assertGreater(res.data["avg_latency_ms"], 0.0)

    def test_variant_info(self):
        # Probar variante individual 1b
        res_1b = self.tool.execute(action="variant_info", variant_name="1b")
        self.assertTrue(res_1b.success, f"Fallo en variant_info 1b: {res_1b.error}")
        self.assertIn("MYTHOS_1B", res_1b.output)
        self.assertEqual(res_1b.data["dim"], 2048)
        self.assertEqual(res_1b.data["loops"], 16)

        # Probar resumen de todas las variantes
        res_all = self.tool.execute(action="variant_info", variant_name="all")
        self.assertTrue(res_all.success)
        self.assertIn("MYTHOS_1B", res_all.output)
        self.assertIn("MYTHOS_1T", res_all.output)
        self.assertIn("1b", res_all.data["variants"])

    def test_compare_transformer(self):
        res = self.tool.execute(action="compare_transformer", dim=64, n_loops=4, attn_type="mla")
        self.assertTrue(res.success, f"Fallo en compare_transformer: {res.error}")
        self.assertIn("Comparativa Arquitectónica", res.output)
        self.assertIn("ahorro de memoria", res.output)
        self.assertGreater(res.data["param_savings_ratio"], 1.0)
        self.assertGreater(res.data["baseline_params"], res.data["mythos_params"])


class TestEnhancedMythosIntegrations(unittest.TestCase):
    def test_loop_phases_presence(self):
        engine = MythosCognitiveEngine()
        self.assertEqual(len(engine.LOOP_PHASES), 4)
        self.assertIn("Exploración Semántica", engine.LOOP_PHASES[0]["name"])
        self.assertIn("Verificación de Restricciones", engine.LOOP_PHASES[1]["name"])
        self.assertIn("Optimización de Rutas", engine.LOOP_PHASES[2]["name"])
        self.assertIn("Consolidación y Síntesis", engine.LOOP_PHASES[3]["name"])

    def test_phase_aware_procedural_memory(self):
        import tempfile
        import shutil
        from jev.core.memory import HierarchicalMemory

        temp_dir = Path(tempfile.mkdtemp())
        try:
            mem = HierarchicalMemory(temp_dir)
            mem.save_solution(
                category="git",
                trigger_keywords="clonar repo git",
                problem_description="Clonar repositorio ligero",
                solution_summary="Usar git clone --depth 1",
                phase="execution"
            )
            # Buscar con fase correspondiente
            res_exec = mem.search_solutions("clonar repo", phase="execution")
            self.assertEqual(len(res_exec), 1)
            self.assertEqual(res_exec[0]["category"], "git")

            # Buscar con fase diferente no relevante
            res_plan = mem.search_solutions("clonar repo", phase="planning")
            self.assertEqual(len(res_plan), 0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

