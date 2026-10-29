"""
Suite de Pruebas Unitarias para la Expansión Modular:
1. Web Sandbox & Visualizador Reactivo (WebBuilderTool & jarvis.html & JarvisBridge).
2. Motor de Modelado 3D Paramétrico (ParametricCadMeshTool, .OBJ, .GLTF y Three.js).
3. Analizador Estocástico y Combinatorio (CombinatorialAnalyticsTool, Hipergeométrica, χ², Shannon, Wheels & Monte Carlo).
4. Integración reflexiva con SkillRegistry y ToolRegistry de JEV.
"""
import unittest
import json
import math
import shutil
from pathlib import Path

from jev.tools.skill_web_builder import WebBuilderTool
from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool
from jev.tools.custom.skill_combinatorial_analytics import CombinatorialAnalyticsTool
from jev.skills.manager import SkillRegistry
from jev.tools.dynamic_loader import DynamicToolManager
from jev.tools.base import ToolRegistry
from app import JarvisBridge
from jev.config import default_config


class TestWebBuilderAndSandbox(unittest.TestCase):
    """Pruebas del Generador Web y el Sandbox Reactivo de JEV."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_web_tmp"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.tool = WebBuilderTool(workspace_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_compile_dashboard_with_tailwind(self):
        """Verifica que el generador web compile un dashboard con Tailwind CDN y Chart.js."""
        res = self.tool.execute(
            template_type="dashboard",
            title="Telemetry Hub",
            theme="dark_cyber",
            components=["navbar", "stat_cards", "charts", "data_table"],
            save_to_workspace=True,
            output_filename="telemetry.html"
        )
        self.assertTrue(res.success)
        self.assertIn("html", res.data)
        html = res.data["html"]
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("https://cdn.tailwindcss.com", html)
        self.assertIn("https://cdn.jsdelivr.net/npm/chart.js", html)
        self.assertIn("Telemetry Hub", html)

        # Verificar archivo en disco
        file_path = Path(res.data["file_path"])
        self.assertTrue(file_path.exists())
        self.assertGreater(file_path.stat().st_size, 500)

    def test_interactive_calculator_template(self):
        """Verifica plantilla de calculadora interactiva."""
        res = self.tool.execute(
            template_type="interactive_calculator",
            title="Cuantificador",
            theme="light_clean",
            save_to_workspace=False
        )
        self.assertTrue(res.success)
        html = res.data["html"]
        self.assertIn("Calculadora Interactiva Reactiva", html)
        self.assertIn("runCompute()", html)

    def test_jarvis_html_web_preview_integration(self):
        """Verifica que jarvis.html contenga el selector de pestañas [Vista Previa Web] y la callback onRenderWebPreview."""
        template_file = Path("jev/ui/templates/jarvis.html")
        self.assertTrue(template_file.exists())
        content = template_file.read_text(encoding="utf-8")

        # Pestaña y vista iframe
        self.assertIn("tabWeb", content)
        self.assertIn("viewWeb", content)
        self.assertIn("webPreviewFrame", content)
        self.assertIn("window.onRenderWebPreview", content)
        self.assertIn("switchArtifactTab('web')", content)

    def test_write_file_auto_routes_to_web_preview(self):
        """Verifica que JarvisBridge enrute automáticamente archivos HTML escritos vía write_file al visor iframe."""
        bridge = JarvisBridge.__new__(JarvisBridge)
        evaluated_scripts = []
        bridge._eval_js = lambda js: evaluated_scripts.append(js)

        # Simular resultado de write_file con archivo HTML
        from jev.tools.base import ToolResult
        sample_html = "<!DOCTYPE html><html><body><h1>Hola JEV</h1></body></html>"
        tool_res = ToolResult(
            success=True,
            output="Archivo guardado",
            data={"path": "workspace/index.html", "content": sample_html}
        )

        bridge._on_tool_result("write_file", tool_res)

        # Debe invocar onRenderCodeArtifact Y onRenderWebPreview
        code_call = any("window.onRenderCodeArtifact" in js for js in evaluated_scripts)
        web_call = any("window.onRenderWebPreview" in js for js in evaluated_scripts)
        self.assertTrue(code_call, "Debe renderizar el código en el visor de artefactos")
        self.assertTrue(web_call, "Debe proyectar el HTML automáticamente en el iframe web")


class TestParametricCadMeshPipeline(unittest.TestCase):
    """Pruebas del Motor de Modelado 3D Paramétrico (CAD & GLTF)."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_cad_tmp"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.tool = ParametricCadMeshTool(workspace_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_spur_gear_and_exports(self):
        """Verifica generación de engranaje recto y exportación a .OBJ, .GLTF y Three.js."""
        res = self.tool.execute(
            model_type="spur_gear",
            name="Test_Pinion",
            parameters={"teeth": 12, "pitch_radius": 2.5, "thickness": 0.8},
            export_formats=["threejs", "obj", "gltf"],
            color="#00f0ff"
        )
        self.assertTrue(res.success, res.error)
        self.assertGreater(res.data["vertex_count"], 20)
        self.assertGreater(res.data["face_count"], 30)

        # Verificar archivo OBJ
        obj_path = Path(res.data["files"]["obj"])
        self.assertTrue(obj_path.exists())
        obj_text = obj_path.read_text(encoding="utf-8")
        self.assertIn("v ", obj_text)
        self.assertIn("vn ", obj_text)
        self.assertIn("f ", obj_text)

        # Verificar archivo GLTF 2.0
        gltf_path = Path(res.data["files"]["gltf"])
        self.assertTrue(gltf_path.exists())
        gltf_json = json.loads(gltf_path.read_text(encoding="utf-8"))
        self.assertEqual(gltf_json["asset"]["version"], "2.0")
        self.assertIn("meshes", gltf_json)
        self.assertIn("buffers", gltf_json)
        self.assertTrue(gltf_json["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,"))

        # Verificar escena Three.js
        scene = res.data["scene"]
        self.assertIn("elements", scene)
        self.assertEqual(scene["elements"][0]["name"], "Test_Pinion")

    def test_generate_helical_spring(self):
        """Verifica generación de resorte helicoidal 3D continuo."""
        res = self.tool.execute(
            model_type="helical_spring",
            name="Suspension_Spring",
            parameters={"radius": 2.0, "pitch": 1.0, "turns": 3.0, "wire_radius": 0.2},
            export_formats=["obj"]
        )
        self.assertTrue(res.success)
        self.assertGreater(res.data["vertex_count"], 100)
        self.assertGreater(res.data["face_count"], 100)

    def test_generate_flange_and_pipe_elbow(self):
        """Verifica generación de brida industrial y codo de tubería."""
        res_flange = self.tool.execute(
            model_type="flange",
            name="Pipe_Flange",
            parameters={"outer_radius": 3.5, "inner_radius": 1.5, "thickness": 0.6}
        )
        self.assertTrue(res_flange.success)

        res_elbow = self.tool.execute(
            model_type="pipe_elbow",
            name="Elbow_90",
            parameters={"radius": 1.0, "bend_radius": 2.5, "angle_deg": 90.0}
        )
        self.assertTrue(res_elbow.success)


class TestCombinatorialAnalyticsEngine(unittest.TestCase):
    """Pruebas del Motor de Analítica Estocástica y Combinatoria."""

    def setUp(self):
        self.tool = CombinatorialAnalyticsTool()

    def test_hypergeometric_exact_odds(self):
        """Verifica cálculo hipergeométrico y consistencia de probabilidad sumatoria = 1.0."""
        res = self.tool.execute(
            action="hypergeometric_odds",
            total_numbers=49,
            pick_count=6
        )
        self.assertTrue(res.success)
        data = res.data["hypergeometric_odds"]
        self.assertEqual(data["total_space_size"], math.comb(49, 6))

        # Suma de probabilidades de todos los aciertos (0 a 6) debe ser exactamente 1.0
        prob_sum = sum(item["probability"] for item in data["distribution"])
        self.assertAlmostEqual(prob_sum, 1.0, places=5)

        # Probabilidad de acertar 6 de 6 = 1 / 13,983,816
        p_6 = data["distribution"][0]["probability"]
        self.assertAlmostEqual(p_6, 1.0 / 13983816.0, places=10)

    def test_chi_square_and_shannon_entropy(self):
        """Verifica bondad de ajuste Chi-cuadrado y entropía sobre muestra sintética."""
        # Generar 100 sorteos sintéticos equilibrados
        draws = []
        for i in range(100):
            # Muestra rotativa balanceada
            draws.append([( (i * 6 + j) % 20 ) + 1 for j in range(6)])

        res = self.tool.execute(
            action="analyze_history",
            total_numbers=20,
            pick_count=6,
            history_data=draws
        )
        self.assertTrue(res.success)
        ha = res.data["historical_analysis"]
        self.assertEqual(ha["total_draws_analyzed"], 100)
        self.assertIn("chi_square_test", ha)
        self.assertIn("shannon_entropy", ha)
        self.assertGreater(ha["shannon_entropy"]["observed_entropy_bits"], 0.0)
        self.assertLessEqual(ha["shannon_entropy"]["entropy_efficiency"], 1.01)

    def test_monte_carlo_ev_calculation(self):
        """Verifica el cálculo de Valor Esperado analítico y simulación Monte Carlo."""
        # Un bote masivo con coste pequeño debe dar EV positivo
        res = self.tool.execute(
            action="monte_carlo_ev",
            total_numbers=20, # Espacio pequeño para permitir aciertos frecuentes en test
            pick_count=4,
            jackpot=500000.0,
            ticket_price=1.0,
            monte_carlo_sims=5000
        )
        self.assertTrue(res.success)
        ev_data = res.data["monte_carlo_ev"]
        self.assertIn("analytical_ev", ev_data)
        self.assertIn("monte_carlo_results", ev_data)
        self.assertTrue(ev_data["is_positive_ev"]) # Con jackpot enorme y N=20, el EV es positivo

    def test_reduced_wheel_covering_design(self):
        """Verifica generación de sistema reducido (Lottery Wheel) con garantía matemática."""
        selected_numbers = [3, 7, 12, 18, 24, 30, 36, 42] # 8 números
        res = self.tool.execute(
            action="generate_reduced_wheel",
            pick_count=6,
            wheel_numbers=selected_numbers,
            wheel_guarantee=4
        )
        self.assertTrue(res.success)
        wheel = res.data["reduced_wheel"]
        # El sistema completo de 8 sobre 6 son 28 boletos
        self.assertEqual(wheel["full_system_tickets"], 28)
        # El sistema reducido debe requerir sustancialmente menos boletos
        self.assertLess(wheel["reduced_system_tickets"], 28)
        self.assertGreater(wheel["reduction_percentage"], 0.0)
        self.assertEqual(wheel["coverage_percentage"], 100.0)


class TestSkillRegistryAndDynamicLoader(unittest.TestCase):
    """Verifica autodescubrimiento y carga de los 3 nuevos dominios en JEV."""

    def test_skills_registered_in_skill_registry(self):
        registry = SkillRegistry()
        skill_names = list(registry._skills.keys())

        self.assertIn("skill_web_builder", skill_names)
        self.assertIn("skill_cad_mesh", skill_names)
        self.assertIn("skill_combinatorial_analytics", skill_names)

    def test_passive_execution_of_new_skills(self):
        registry = SkillRegistry()

        # 1. skill_web_builder
        res_web = registry.execute_skill("skill_web_builder", title="Unit Test Page", save_to_workspace=False)
        self.assertEqual(res_web.get("status"), "success")

        # 2. skill_cad_mesh
        res_cad = registry.execute_skill("skill_cad_mesh", model_type="spur_gear", export_formats=["threejs"])
        self.assertEqual(res_cad.get("status"), "success")

        # 3. skill_combinatorial_analytics
        res_stoch = registry.execute_skill("skill_combinatorial_analytics", action="hypergeometric_odds", total_numbers=25, pick_count=5)
        self.assertEqual(res_stoch.get("status"), "success")

    def test_dynamic_tool_manager_loads_custom_tools(self):
        tool_reg = ToolRegistry()
        dyn_mgr = DynamicToolManager(tool_reg)
        loaded = dyn_mgr.load_all()

        self.assertIn("skill_cad_mesh", loaded)
        self.assertIn("skill_combinatorial_analytics", loaded)


if __name__ == "__main__":
    unittest.main()
