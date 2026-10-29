"""
Pruebas unitarias de la Extensión Arquitectural y Motor de Capacidades Autónomas (JEV v2.5):
1. FASE 1: Entorno de Visualización Dual & Bridge 3D Artifacts
2. FASE 2: Bucle Obligatorio de Autocrítica, Corrección (Post-Execution) y Tool Gap Analysis
3. FASE 3: Sistema Modular de Habilidades (Skill Factory & Registry) y Skills Iniciales
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jev.core.agent import AgentCore
from jev.core.llm_client import LLMResponse
from jev.core.post_reflection import PostExecutionAuditEngine, AuditResult, ToolGapReport
from jev.skills.manager import SkillRegistry, SkillFactory, SkillMetadata
from jev.skills.skill_mesh_generator.handler import handle as mesh_generator_handle
from jev.skills.skill_net_diagnostics.handler import handle as net_diagnostics_handle
from jev.skills.skill_code_linter.handler import handle as code_linter_handle
from jev.config import AgentConfig
from app import JarvisBridge


class TestArchitectureUpgradeV25(unittest.TestCase):

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
        self.agent = AgentCore(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- FASE 1: DUAL VIEWPORT & 3D BRIDGE ---
    def test_01_jarvis_bridge_artifacts_methods(self):
        """Verifica que JarvisBridge exponga los métodos de renderizado de artefactos y eventos de viewport."""
        bridge = JarvisBridge(self.config)
        mock_window = MagicMock()
        bridge.set_window(mock_window)

        # 1. Renderizar escena 3D
        test_scene = {"elements": [{"type": "mesh", "name": "TestCube"}]}
        bridge.render_3d_scene(test_scene)
        mock_window.evaluate_js.assert_called()
        last_js = mock_window.evaluate_js.call_args[0][0]
        self.assertIn("window.onRender3DScene", last_js)
        self.assertIn("TestCube", last_js)

        # 2. Renderizar código en el panel
        bridge.render_code_artifact("print('Holo')", "holo.py")
        last_js_code = mock_window.evaluate_js.call_args[0][0]
        self.assertIn("window.onRenderCodeArtifact", last_js_code)
        self.assertIn("holo.py", last_js_code)

        # 3. Recibir evento del viewport desde Three.js
        bridge.on_viewport_event("mesh_selected", {"name": "TestCube", "position": [0, 0, 0]})

    # --- FASE 2: AUDIT & CRITIQUE Y TOOL GAP ANALYSIS ---
    def test_02_post_execution_audit_detects_placeholders(self):
        """Verifica que el submódulo de auditoría detecte funciones vacías y placeholders en código generado."""
        audit_engine = PostExecutionAuditEngine(llm_client=None)

        # Código incompleto con pass
        bad_code = "def process_data(items):\n    # TODO: implementar\n    pass\n"
        res: AuditResult = audit_engine.audit_and_critique(
            user_goal="Crear función de procesamiento",
            final_answer=f"Aquí está el código:\n```python\n{bad_code}```",
            written_files=[("process.py", bad_code)],
            tools_used=["write_file"]
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("placeholder incompleto" in issue for issue in res.issues))

    def test_03_post_execution_audit_passes_valid_code(self):
        """Verifica que código completo sin placeholders pase la auditoría exitosamente."""
        audit_engine = PostExecutionAuditEngine(llm_client=None)
        good_code = "def process_data(items):\n    return [x * 2 for x in items]\n"

        res: AuditResult = audit_engine.audit_and_critique(
            user_goal="Crear función de duplicación",
            final_answer=f"Código listo:\n```python\n{good_code}```",
            written_files=[("process.py", good_code)],
            tools_used=["write_file"]
        )
        self.assertTrue(res.passed)
        self.assertEqual(len(res.issues), 0)

    def test_04_tool_gap_analysis_identifies_missing_capabilities(self):
        """Verifica que se identifiquen brechas operativas para sugerir nuevas herramientas."""
        audit_engine = PostExecutionAuditEngine(llm_client=None)

        # Meta de red sin haber usado skill_net_diagnostics
        gap_report: ToolGapReport = audit_engine.tool_gap_analysis(
            user_goal="Medir la latencia y RTT hacia 8.8.8.8",
            tools_used=["execute_command"],
            success=True
        )
        self.assertTrue(gap_report.has_gap)
        self.assertEqual(gap_report.gap_name, "skill_net_diagnostics")

        # Meta 3D sin haber usado skill_mesh_generator
        gap_3d: ToolGapReport = audit_engine.tool_gap_analysis(
            user_goal="Generar una malla 3D procedural para Three.js",
            tools_used=["write_file"],
            success=True
        )
        self.assertTrue(gap_3d.has_gap)
        self.assertEqual(gap_3d.gap_name, "skill_mesh_generator")

    # --- FASE 3: SKILL REGISTRY & INITIAL SKILLS ---
    def test_05_skill_mesh_generator_outputs_valid_threejs_json(self):
        """Verifica que skill_mesh_generator cree geometrías compatibles con Three.js."""
        res = mesh_generator_handle(shape="box", params={"width": 4, "color": "#00ff88"})
        self.assertEqual(res["status"], "success")
        self.assertIn("scene", res)
        self.assertIn("elements", res["scene"])
        box_elem = res["element"]
        self.assertEqual(box_elem["geometry"]["type"], "BoxGeometry")
        self.assertEqual(box_elem["material"]["color"], "#00ff88")

    def test_06_skill_net_diagnostics_executes_tcp_and_dns(self):
        """Verifica que skill_net_diagnostics ejecute resolución DNS y ping TCP."""
        res_dns = net_diagnostics_handle(action="dns_resolve", target="127.0.0.1")
        self.assertTrue(res_dns["success"])
        self.assertIn("127.0.0.1", res_dns["resolved_ips"])

        res_ping = net_diagnostics_handle(action="tcp_ping", target="127.0.0.1", port=80, count=1, timeout=0.5)
        self.assertIn("target", res_ping)

    def test_07_skill_code_linter_ast_verification(self):
        """Verifica que skill_code_linter reporte errores de sintaxis y placeholders."""
        res_syntax = code_linter_handle(code="def foo(:\n  return 1")
        self.assertFalse(res_syntax["valid"])
        self.assertEqual(res_syntax["errors"][0]["type"], "SyntaxError")

        res_ok = code_linter_handle(code="def bar():\n  return 42\n")
        self.assertTrue(res_ok["valid"])

    def test_08_skill_factory_creates_and_tests_new_skill(self):
        """Verifica que SkillFactory compile, valide y registre una nueva habilidad en disco."""
        temp_skills_dir = self.temp_dir / "custom_skills"
        temp_skills_dir.mkdir(parents=True)
        registry = SkillRegistry(skills_dir=temp_skills_dir)
        factory = SkillFactory(registry)

        handler_code = "def handle(x: int = 1) -> dict:\n    return {'result': x * 10}\n"
        test_code = "import unittest\nfrom handler import handle\nclass TestCustom(unittest.TestCase):\n    def test_run(self):\n        self.assertEqual(handle(2)['result'], 20)\nif __name__ == '__main__':\n    unittest.main()\n"

        new_skill = factory.create_skill(
            name="skill_test_multiplier",
            description="Multiplicador de prueba",
            handler_code=handler_code,
            test_code=test_code,
            category="math"
        )
        self.assertIsNotNone(new_skill)
        self.assertEqual(new_skill.name, "skill_test_multiplier")
        self.assertEqual(new_skill.execute(x=5)["result"], 50)
        self.assertTrue(registry.run_skill_tests("skill_test_multiplier"))

    def test_09_agent_core_integrates_skills_as_tools(self):
        """Verifica que AgentCore integre automáticamente las habilidades registradas en su ToolRegistry."""
        self.assertIsNotNone(self.agent.registry.get("skill_mesh_generator"))
        self.assertIsNotNone(self.agent.registry.get("skill_net_diagnostics"))
        self.assertIsNotNone(self.agent.registry.get("skill_code_linter"))

        # Ejecutar herramienta desde el registry
        res = self.agent.registry.execute_call("skill_mesh_generator", {"shape": "sphere", "params": {"radius": 2}})
        self.assertTrue(res.success)
        self.assertIn("SphereGeometry", res.output)


if __name__ == "__main__":
    unittest.main()
