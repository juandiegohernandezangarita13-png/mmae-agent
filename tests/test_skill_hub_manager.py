"""
Suite de Pruebas Unitarias para el Meta-Gestor Dinámico de Habilidades (SkillHubManagerTool):
1. Auditoría estática AST y detección de llamadas prohibidas (os.system, subprocess shell=True, eval/exec).
2. Ejecución y validación aislada de pruebas unitarias en sandbox antes de autorización.
3. Búsqueda semántica, descarga e inyección en caliente en SkillRegistry y ToolRegistry.
4. Integración con el Bucle de Autocrítica y Tool Gap Analysis de SelfImprovementEvaluator.
5. Verificación del comando de consola /skills-update y listado de inventario.
"""
import unittest
import shutil
import json
from pathlib import Path

from jev.tools.custom.skill_hub_manager import (
    SkillHubManagerTool,
    SecurityAuditor,
    SandboxTestRunner,
    COMMUNITY_SKILLS_CATALOG
)
from jev.skills.manager import SkillRegistry
from jev.tools.base import ToolRegistry, get_skill_hub_manager_tool
from jev.self_improvement.evaluator import SelfImprovementEvaluator
from jev.core.memory import HierarchicalMemory
from jev.core.llm_client import LocalLLMClient
from jev.config import AgentConfig


class TestSecurityAuditor(unittest.TestCase):
    """Pruebas de inspección estática AST sobre código de habilidades entrantes."""

    def setUp(self):
        self.tmp_dir = Path("data/cache/test_auditor_pkg")
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        (self.tmp_dir / "tests").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_clean_package_passes_audit(self):
        """Un paquete con estructura estándar y código limpio aprueba la auditoría."""
        (self.tmp_dir / "metadata.json").write_text(json.dumps({
            "name": "skill_clean",
            "version": "1.0.0",
            "description": "Habilidad segura"
        }), encoding="utf-8")

        (self.tmp_dir / "handler.py").write_text("""
def handle(**kwargs):
    return {"status": "ok", "result": 42}
""", encoding="utf-8")

        (self.tmp_dir / "tests" / "test_handler.py").write_text("""
import unittest
class TestClean(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
""", encoding="utf-8")

        safe, violations = SecurityAuditor.audit_package(self.tmp_dir)
        self.assertTrue(safe, f"Violaciones inesperadas: {violations}")
        self.assertEqual(len(violations), 0)

    def test_os_system_call_is_rejected(self):
        """Detecta y rechaza código malicioso con 'os.system'."""
        (self.tmp_dir / "metadata.json").write_text(json.dumps({
            "name": "skill_malicious_os",
            "version": "1.0.0",
            "description": "Intento de ejecución arbitraria"
        }), encoding="utf-8")

        (self.tmp_dir / "handler.py").write_text("""
import os
def handle(**kwargs):
    os.system("echo hacked")
    return {"status": "bad"}
""", encoding="utf-8")

        (self.tmp_dir / "tests" / "test_handler.py").write_text("""
import unittest
class Test(unittest.TestCase): pass
""", encoding="utf-8")

        safe, violations = SecurityAuditor.audit_package(self.tmp_dir)
        self.assertFalse(safe)
        self.assertTrue(any("os.system" in v for v in violations))

    def test_subprocess_shell_true_is_rejected(self):
        """Detecta y rechaza subprocess con shell=True."""
        (self.tmp_dir / "metadata.json").write_text(json.dumps({
            "name": "skill_shell_true",
            "version": "1.0.0",
            "description": "Shell injection risk"
        }), encoding="utf-8")

        (self.tmp_dir / "handler.py").write_text("""
import subprocess
def handle(**kwargs):
    subprocess.run("dir", shell=True)
    return {"status": "bad"}
""", encoding="utf-8")

        (self.tmp_dir / "tests" / "test_handler.py").write_text("""
import unittest
class Test(unittest.TestCase): pass
""", encoding="utf-8")

        safe, violations = SecurityAuditor.audit_package(self.tmp_dir)
        self.assertFalse(safe)
        self.assertTrue(any("shell=True" in v for v in violations))

    def test_eval_exec_is_rejected(self):
        """Detecta y rechaza funciones dinámicas inseguras como eval o exec."""
        (self.tmp_dir / "metadata.json").write_text(json.dumps({
            "name": "skill_eval",
            "version": "1.0.0",
            "description": "Eval risk"
        }), encoding="utf-8")

        (self.tmp_dir / "handler.py").write_text("""
def handle(**kwargs):
    payload = kwargs.get("code", "")
    return {"res": eval(payload)}
""", encoding="utf-8")

        (self.tmp_dir / "tests" / "test_handler.py").write_text("""
import unittest
class Test(unittest.TestCase): pass
""", encoding="utf-8")

        safe, violations = SecurityAuditor.audit_package(self.tmp_dir)
        self.assertFalse(safe)
        self.assertTrue(any("eval" in v for v in violations))


class TestSandboxTestRunner(unittest.TestCase):
    """Pruebas de aislamiento y ejecución en sandbox antes de registrar habilidades."""

    def setUp(self):
        self.pkg_dir = Path("data/cache/test_sandbox_pkg")
        if self.pkg_dir.exists():
            shutil.rmtree(self.pkg_dir, ignore_errors=True)
        self.pkg_dir.mkdir(parents=True, exist_ok=True)
        (self.pkg_dir / "tests").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.pkg_dir.exists():
            shutil.rmtree(self.pkg_dir, ignore_errors=True)

    def test_failing_unit_tests_blocked(self):
        """Una habilidad cuyas pruebas unitarias fallen no debe autorizarse."""
        (self.pkg_dir / "handler.py").write_text("def handle(**kwargs): return 1", encoding="utf-8")
        (self.pkg_dir / "tests" / "test_failing.py").write_text("""
import unittest
class TestFail(unittest.TestCase):
    def test_will_fail(self):
        self.assertEqual(1, 2, "Test deliberadamente roto")
""", encoding="utf-8")

        passed, msg = SandboxTestRunner.run_isolated_tests(self.pkg_dir, "skill_failing")
        self.assertFalse(passed)
        self.assertIn("Fallos", msg)


class TestSkillHubManagerCore(unittest.TestCase):
    """Pruebas funcionales de búsqueda, instalación y ciclo de vida de habilidades."""

    def setUp(self):
        self.skill_reg = SkillRegistry()
        self.tool_reg = ToolRegistry()
        self.events_received = []

        def _on_event(ev_type, data):
            self.events_received.append((ev_type, data))

        self.hub = SkillHubManagerTool(
            skill_registry=self.skill_reg,
            tool_registry=self.tool_reg,
            on_event=_on_event
        )

    def tearDown(self):
        # Limpiar posibles habilidades instaladas de prueba si es necesario
        for sk in ["skill_quantum_circuit_sim", "skill_database_query_optimizer", "skill_cryptographic_vault"]:
            shutil.rmtree(Path("data/cache/incoming_skills") / sk, ignore_errors=True)

    def test_search_skills_semantic(self):
        """Verifica coincidencia semántica en el catálogo comunitario."""
        # 1. Búsqueda de computación cuántica
        matches_q = self.hub.search("simulación de circuitos cuánticos con qubits y superposición")
        self.assertGreater(len(matches_q), 0)
        self.assertEqual(matches_q[0]["name"], "skill_quantum_circuit_sim")

        # 2. Búsqueda de optimización de bases de datos
        matches_sql = self.hub.search("optimizar consultas SQL lentas y auditoría de índices")
        self.assertGreater(len(matches_sql), 0)
        self.assertEqual(matches_sql[0]["name"], "skill_database_query_optimizer")

        # 3. Búsqueda de criptografía y hashing
        matches_crypto = self.hub.search("generar firma criptográfica sha256 y bóveda de claves")
        self.assertGreater(len(matches_crypto), 0)
        self.assertEqual(matches_crypto[0]["name"], "skill_cryptographic_vault")

    def test_install_quantum_skill_hot_injection(self):
        """Descarga, audita, prueba en sandbox e inyecta skill_quantum_circuit_sim en caliente."""
        res = self.hub.execute(action="install", skill_name="skill_quantum_circuit_sim")
        self.assertTrue(res.success, f"Fallo al instalar: {res.error}")
        self.assertEqual(res.data.get("status"), "installed_active")

        # Verificar evento emitido al DAG
        self.assertTrue(any(ev[0] == "skill_auto_injected" for ev in self.events_received))
        event_entry = next(ev for ev in self.events_received if ev[0] == "skill_auto_injected")
        self.assertIn("skill_quantum_circuit_sim", event_entry[1]["message"])

        # Verificar que el SkillRegistry la descubrió
        skill = self.skill_reg.get_skill("skill_quantum_circuit_sim")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.metadata.category, "quantum_computing")

        # Verificar ejecución directa de la nueva habilidad
        sim_res = self.skill_reg.execute_skill(
            "skill_quantum_circuit_sim",
            action="simulate_circuit",
            num_qubits=2,
            gates=[
                {"gate": "H", "target": 0},
                {"gate": "CNOT", "control": 0, "target": 1}
            ]
        )
        self.assertEqual(sim_res.get("status"), "success")
        self.assertIn("|00>", sim_res.get("probabilities", {}))
        self.assertIn("|11>", sim_res.get("probabilities", {}))

    def test_search_and_install_resolves_gap(self):
        """Verifica búsqueda e instalación automática ante una necesidad declarada."""
        res = self.hub.execute(
            action="search_and_install",
            task_description="necesito un analizador para optimizar queries SQL con problemas de rendimiento"
        )
        self.assertTrue(res.success, f"Error: {res.error}")
        self.assertEqual(res.data.get("skill_name"), "skill_database_query_optimizer")

        # Probar la herramienta instalada
        opt_res = self.skill_reg.execute_skill(
            "skill_database_query_optimizer",
            query="SELECT * FROM transactions WHERE amount > 1000;"
        )
        self.assertEqual(opt_res.get("status"), "success")
        self.assertFalse(opt_res.get("is_production_ready"))

    def test_list_hub_inventory(self):
        """Verifica inventario de skills activas vs disponibles."""
        inv = self.hub.list_hub_inventory()
        self.assertIn("installed_count", inv)
        self.assertIn("installed_skills", inv)
        self.assertIn("available_in_hub", inv)
        self.assertGreater(len(inv["available_in_hub"]), 0)


class TestToolGapAnalysisIntegration(unittest.TestCase):
    """Pruebas de auto-detección de carencias y resolución en SelfImprovementEvaluator."""

    def test_evaluator_resolves_gap_and_records_lesson(self):
        """Verifica que el evaluador dispare la instalación y registre la lección aprendida."""
        mem = HierarchicalMemory()
        cfg = AgentConfig()
        llm = LocalLLMClient(cfg)
        thought_logs = []

        def _on_thought(t):
            thought_logs.append(t)

        evaluator = SelfImprovementEvaluator(
            memory=mem,
            llm_client=llm,
            on_thought=_on_thought
        )

        # Resolver carencia
        gap_desc = "bóveda de claves criptográficas y generación segura de hashes HMAC sha256"
        data = evaluator.resolve_tool_gap(gap_desc, task_context="Tarea de seguridad de tokens")
        self.assertIsNotNone(data)
        self.assertEqual(data.get("skill_name"), "skill_cryptographic_vault")

        # Verificar que se emitió el pensamiento / evento
        self.assertTrue(any("⚡ [Skill Auto-Injected]" in t for t in thought_logs))

        # Verificar lección persistida en memoria
        lessons = mem.get_all_lessons()
        gap_lessons = [l for l in lessons if "skill_cryptographic_vault" in l.get("rule", "")]
        self.assertGreater(len(gap_lessons), 0)
        self.assertEqual(gap_lessons[-1]["category"], "Herramientas")

    def test_factory_function_in_base(self):
        """Verifica que get_skill_hub_manager_tool retorne una instancia válida."""
        tool = get_skill_hub_manager_tool()
        self.assertEqual(tool.name, "skill_hub_manager")
        self.assertTrue(hasattr(tool, "execute"))


if __name__ == "__main__":
    unittest.main()
