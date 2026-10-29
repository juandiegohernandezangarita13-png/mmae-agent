"""
Suite de Pruebas Unitarias para el Motor de Edición Atómica de Proyectos y Sandbox Branching (Plandex-Style Engine):
1. Mapeador Sintáctico de Repositorio (ASTContextSlicer): Extracción de esqueletos y slices sin cuerpos.
2. Espacio de Ensayo Aislado (SandboxStagingManager): Staging temporal en .jev_staging/<plan_id>/.
3. Validador de Diffs y Confirmación Atómica (AtomicCommitEngine):
   - Reversión atómica y protección contra sobreescritura ante fallos de sintaxis.
   - Fusión atómica exitosa cuando la validación pasa.
   - Descarte limpio de rama en rollback manual.
4. Herramienta RepoPlannerTool e integración de fábrica get_repo_planner_tool.
5. Descubrimiento e indexación en el SkillRegistry de JEV (21ª habilidad).
6. Integración reactiva en JarvisBridge._on_tool_result y proyección de changes.diff.
"""
import unittest
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from jev.tools.custom.skill_repo_planner import (
    ASTContextSlicer,
    SandboxStagingManager,
    AtomicCommitEngine,
    RepoPlannerTool
)
from jev.tools.base import get_repo_planner_tool, ToolResult
from jev.skills.manager import SkillRegistry
from jev.config import default_config, AgentConfig
from app import JarvisBridge


class TestASTContextSlicer(unittest.TestCase):
    """Pruebas de mapeo sintáctico y extracción de rebanadas de contexto."""

    SAMPLE_PYTHON_CODE = '''"""Módulo de autenticación y seguridad."""
import os
import hashlib
from typing import Optional, Dict

GLOBAL_TIMEOUT: int = 300

class AuthService:
    """Servicio central de autenticación y tokens."""

    def __init__(self, secret_key: str = "default_secret") -> None:
        """Inicializa credenciales."""
        self.secret_key = secret_key
        self.active_sessions: Dict[str, str] = {}

    def generate_token(self, username: str, salt: str = "salt") -> str:
        """Genera token SHA-256 para el usuario."""
        raw = f"{username}:{salt}:{self.secret_key}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def verify_token_async(self, token: str) -> bool:
        """Verifica validez asíncrona del token."""
        return token in self.active_sessions

def validate_email(email: str) -> bool:
    """Valida formato básico de correo electrónico."""
    return "@" in email and "." in email
'''

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_slicer_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_file = self.test_dir / "auth_service.py"
        self.test_file.write_text(self.SAMPLE_PYTHON_CODE, encoding="utf-8")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_extract_python_outline_omits_bodies(self):
        """Verifica que el outline extrae clases, métodos y docstrings omitiendo cuerpos."""
        symbols, skeleton, orig_lines, skel_lines = ASTContextSlicer.extract_python_outline(
            self.SAMPLE_PYTHON_CODE, "auth_service.py"
        )

        self.assertGreaterEqual(len(symbols), 2)  # AuthService y validate_email
        class_sym = next(s for s in symbols if s.name == "AuthService")
        self.assertEqual(class_sym.kind, "class")
        self.assertIn("Servicio central", class_sym.docstring)
        self.assertEqual(len(class_sym.children), 3)  # __init__, generate_token, verify_token_async

        # Verificar que el esqueleto omitió cuerpos y redujo líneas
        self.assertIn("Cuerpo omitido", skeleton)
        self.assertNotIn("hashlib.sha256(raw.encode())", skeleton)
        self.assertLess(skel_lines, orig_lines)

    def test_slice_file_reduction_metrics(self):
        """Verifica las métricas de reducción de contexto de un archivo individual."""
        res = ASTContextSlicer.slice_file(self.test_file)
        self.assertIn("context_reduction_percent", res)
        self.assertGreater(res["context_reduction_percent"], 20.0)
        self.assertGreater(res["symbols_count"], 0)

    def test_get_slice_by_symbol(self):
        """Verifica la extracción quirúrgica de una función específica."""
        slice_res = ASTContextSlicer.get_slice(self.test_file, symbol_name="generate_token")
        self.assertEqual(slice_res["symbol_name"], "generate_token")
        self.assertIn("def generate_token", slice_res["slice_content"])
        self.assertIn("hashlib.sha256", slice_res["slice_content"])

    def test_scan_repository(self):
        """Verifica el escaneo jerárquico completo del repositorio."""
        repo_res = ASTContextSlicer.scan_repository(self.test_dir)
        self.assertGreaterEqual(repo_res["total_files"], 1)
        self.assertGreaterEqual(repo_res["total_symbols"], 2)
        self.assertIn("global_context_reduction_percent", repo_res)


class TestSandboxStaging(unittest.TestCase):
    """Pruebas del entorno de ensayo aislado en .jev_staging/<plan_id>/."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_staging_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.staging_mgr = SandboxStagingManager(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_plan_and_isolation(self):
        """Verifica que el plan de staging se cree en .jev_staging y aísle los cambios."""
        plan = self.staging_mgr.create_plan("plan_refactor_01", description="Refactorización segura")
        self.assertEqual(plan["plan_id"], "plan_refactor_01")
        self.assertEqual(plan["status"], "active")

        plan_dir = self.staging_mgr.get_plan_dir("plan_refactor_01")
        self.assertTrue(plan_dir.exists())
        self.assertTrue((plan_dir / "metadata.json").exists())

    def test_stage_file_does_not_modify_main_workspace(self):
        """Comprueba que escribir en staging no modifique el archivo principal del workspace."""
        orig_file = self.test_dir / "config.json"
        orig_file.write_text('{"env": "production", "debug": false}', encoding="utf-8")

        # Staging de una versión modificada
        staged_content = '{"env": "development", "debug": true, "feature_flag": true}'
        res = self.staging_mgr.stage_file("plan_refactor_01", "config.json", staged_content)

        self.assertEqual(res["status"], "staged")
        # El workspace original debe seguir con su contenido anterior intacto
        self.assertEqual(orig_file.read_text(encoding="utf-8"), '{"env": "production", "debug": false}')

        # El staging contiene la versión modificada
        staged_copy = self.staging_mgr.get_plan_dir("plan_refactor_01") / "files" / "config.json"
        self.assertEqual(staged_copy.read_text(encoding="utf-8"), staged_content)

    def test_unified_diff_generation(self):
        """Verifica que get_diff genere un parche unified diff estándar."""
        orig_file = self.test_dir / "module.py"
        orig_file.write_text("def run():\n    return 1\n", encoding="utf-8")

        staged_content = "def run():\n    # Mejorado\n    return 2\n"
        self.staging_mgr.stage_file("plan_diff_test", "module.py", staged_content)

        diff_res = self.staging_mgr.get_diff("plan_diff_test")
        self.assertEqual(diff_res["files_count"], 1)
        self.assertGreater(diff_res["total_insertions"], 0)
        self.assertIn("--- a/module.py", diff_res["diff_text"])
        self.assertIn("+++ b/module.py", diff_res["diff_text"])
        self.assertIn("+    return 2", diff_res["diff_text"])


class TestAtomicCommitAndRollback(unittest.TestCase):
    """Pruebas de validación sintáctica, reversión atómica y confirmación segura."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_atomic_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.staging_mgr = SandboxStagingManager(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_rollback_on_syntax_error(self):
        """
        PRUEBA CRÍTICA: Ante código propuesto con errores de sintaxis, el commit
        debe fallar, abortar y ejecutar rollback automático, dejando el archivo original
        del workspace completamente intacto.
        """
        # 1. Crear archivo original válido en workspace
        main_file = self.test_dir / "engine.py"
        original_code = "def compute_velocity(x: float) -> float:\n    return x * 9.8\n"
        main_file.write_text(original_code, encoding="utf-8")

        # 2. Staging de código corrupto con error deliberado de sintaxis
        corrupt_code = "def compute_velocity(x: float) -> float:\n    return x * 9.8 +++ syntax_error (((\n"
        self.staging_mgr.stage_file("plan_broken", "engine.py", corrupt_code)

        # 3. Intentar commit
        commit_res = AtomicCommitEngine.commit_plan(self.staging_mgr, "plan_broken")

        # 4. Validar que el commit fue rechazado y marcado como rollback
        self.assertFalse(commit_res["success"], "El commit debe fallar si hay errores de sintaxis")
        self.assertTrue(commit_res.get("rolled_back"), "Debe haberse ejecutado rollback automático")
        self.assertGreater(len(commit_res.get("syntax_errors", [])), 0)

        # 5. VERIFICACIÓN DE INTEGRIDAD: El archivo original del workspace sigue intacto
        self.assertEqual(
            main_file.read_text(encoding="utf-8"),
            original_code,
            "El archivo original en el workspace no debe haber sido tocado ni corrompido."
        )

    def test_atomic_commit_on_valid_code(self):
        """Verifica que cuando el código en staging es sintácticamente válido, se fusiona atómicamente."""
        main_file = self.test_dir / "calculator.py"
        main_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        # Staging de código mejorado y sintácticamente impecable
        improved_code = "def add(a: int, b: int) -> int:\n    \"\"\"Suma tipada.\"\"\"\n    return a + b\n"
        self.staging_mgr.stage_file("plan_valid", "calculator.py", improved_code)

        # Confirmar plan
        commit_res = AtomicCommitEngine.commit_plan(self.staging_mgr, "plan_valid")

        self.assertTrue(commit_res["success"])
        self.assertIn("calculator.py", commit_res["files_committed"])
        # El archivo principal fue actualizado
        self.assertEqual(main_file.read_text(encoding="utf-8"), improved_code)
        # El staging fue limpiado
        self.assertFalse(self.staging_mgr.get_plan_dir("plan_valid").exists())

    def test_manual_rollback_cleans_staging(self):
        """Verifica que rollback_plan descarte la rama de staging sin alterar workspace."""
        main_file = self.test_dir / "service.py"
        main_file.write_text("ACTIVE = True\n", encoding="utf-8")

        self.staging_mgr.stage_file("plan_abort", "service.py", "ACTIVE = False\n")
        self.assertTrue(self.staging_mgr.get_plan_dir("plan_abort").exists())

        rb_res = AtomicCommitEngine.rollback_plan(self.staging_mgr, "plan_abort")
        self.assertTrue(rb_res["success"])
        self.assertFalse(self.staging_mgr.get_plan_dir("plan_abort").exists())
        self.assertEqual(main_file.read_text(encoding="utf-8"), "ACTIVE = True\n")


class TestRepoPlannerTool(unittest.TestCase):
    """Pruebas funcionales de RepoPlannerTool y fábrica get_repo_planner_tool."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_tool_repo_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.tool = RepoPlannerTool(workspace_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tool_lifecycle(self):
        """Verifica el ciclo completo de acciones: create_plan -> stage_file -> get_diff -> commit_plan."""
        # 1. Crear plan
        res_create = self.tool.execute(action="create_plan", plan_id="feature_math")
        self.assertTrue(res_create.success)

        # 2. Stage file
        res_stage = self.tool.execute(
            action="stage_file",
            plan_id="feature_math",
            target_path="math_utils.py",
            content="def multiply(x: int, y: int) -> int:\n    return x * y\n"
        )
        self.assertTrue(res_stage.success)

        # 3. Get diff
        res_diff = self.tool.execute(action="get_diff", plan_id="feature_math")
        self.assertTrue(res_diff.success)
        self.assertIn("multiply", res_diff.output)

        # 4. Commit plan
        res_commit = self.tool.execute(action="commit_plan", plan_id="feature_math")
        self.assertTrue(res_commit.success)
        self.assertTrue((self.test_dir / "math_utils.py").exists())

    def test_factory_function(self):
        """Verifica la fábrica get_repo_planner_tool."""
        tool = get_repo_planner_tool()
        self.assertEqual(tool.__class__.__name__, "RepoPlannerTool")
        self.assertEqual(tool.name, "skill_repo_planner")


class TestSkillRegistryIntegration(unittest.TestCase):
    """Pruebas de indexación en el SkillRegistry como la 21ª habilidad."""

    def test_skill_repo_planner_discovered(self):
        """Verifica que el SkillRegistry indexe skill_repo_planner."""
        registry = SkillRegistry()
        skill = registry.get_skill("skill_repo_planner")

        self.assertIsNotNone(skill, "skill_repo_planner debe ser indexada por SkillRegistry")
        self.assertEqual(skill.metadata.name, "skill_repo_planner")
        self.assertEqual(skill.metadata.category, "code_engineering")
        self.assertIn("refactorizacion", skill.metadata.trigger_keywords)

    def test_skill_execution_via_registry(self):
        """Verifica la ejecución modular mediante SkillRegistry.execute_skill."""
        registry = SkillRegistry()
        res = registry.execute_skill(
            "skill_repo_planner",
            action="create_plan",
            plan_id="registry_plan_test"
        )
        self.assertEqual(res.get("status"), "success")


class TestJarvisBridgeDiffRendering(unittest.TestCase):
    """Pruebas de proyección de changes.diff y telemetría reactiva en JarvisBridge."""

    def test_on_tool_result_renders_diff_and_notifies(self):
        """Verifica que JarvisBridge proyecte diffs en el visor de artefactos de código."""
        cfg = AgentConfig()
        bridge = JarvisBridge(cfg)
        bridge._on_thought = MagicMock()
        bridge._eval_js = MagicMock()

        result = ToolResult(
            success=True,
            output="Diff calculado",
            data={
                "plan_id": "refactor_security",
                "files_count": 2,
                "diff_text": "--- a/auth.py\n+++ b/auth.py\n@@ -1,2 +1,3 @@\n+import bcrypt\n"
            }
        )

        bridge._on_tool_result("skill_repo_planner", result)

        # 1. Comprobar que evaluó JS para renderizar changes.diff en la pestaña de código
        bridge._eval_js.assert_called()
        js_calls = [str(call[0][0]) for call in bridge._eval_js.call_args_list]
        self.assertTrue(any("onRenderCodeArtifact" in j and "changes.diff" in j for j in js_calls))

        # 2. Comprobar notificación en stream de pensamientos
        bridge._on_thought.assert_called()
        thought_calls = [str(call[0][0]) for call in bridge._on_thought.call_args_list]
        self.assertTrue(any("Plandex Staging" in t and "refactor_security" in t for t in thought_calls))


if __name__ == "__main__":
    unittest.main()
