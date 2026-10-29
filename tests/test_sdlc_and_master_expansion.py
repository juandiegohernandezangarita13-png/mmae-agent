"""
Suite de Pruebas Automatizadas para la Directiva Maestra de Expansión Total:
1. Monitor Canario de Contexto y Resiliencia Cognitiva (jev/core/agent.py)
2. Protocolo SDLC Senior con Checkpoints, Auto Red-Teaming y Cobertura >= 80% (skill_sdlc_senior)
3. Suite OSINT en Terminal y Multi-Vector Intelligence (skill_osint_investigator)
4. Motor de Diseño Web Anti-Genericidad Pro Max con 68 Temas y WCAG (skill_web_design_pro)
"""
import unittest
import json
import os
from pathlib import Path

from jev.core.agent import AgentCore
from jev.config import AgentConfig
from jev.tools.custom.skill_sdlc_senior import (
    SDLCSeniorTool,
    SDLCPlanner,
    SDLCSecurityAuditor,
    SDLCTestCoverageEnforcer
)
from jev.tools.custom.skill_osint_toolkit import (
    OSINTToolkitTool,
    EmailIdentityInvestigator,
    OnionGraphCrawler,
    MultiVectorInvestigator
)
from jev.tools.custom.skill_web_design_pro import (
    WebDesignProTool,
    ThemeRegistry,
    AntiGenericQualityEngine,
    ProWebGenerator
)
from jev.tools import build_default_registry


class TestCanaryContextMonitor(unittest.TestCase):
    """Pruebas del Monitor Canario de Contexto en el núcleo cognitivo."""

    def setUp(self):
        self.config = AgentConfig(workspace_dir="workspace", model_name="mock-model")
        self.agent = AgentCore(config=self.config)

    def test_canary_token_present_in_system_prompt(self):
        prompt = self.agent._build_system_prompt()
        self.assertIn("CANARY::JEV_ACTIVE_CTX", prompt)
        self.assertIn("MONITOR CANARIO DE CONTEXTO", prompt)

    def test_verify_canary_success_and_failure(self):
        valid_response = "CANARY::JEV_ACTIVE_CTX [Plan]: Ejecutar paso 1 de forma óptima."
        invalid_response = "[Plan]: Ejecutar paso 1 sin el centinela."

        self.assertTrue(self.agent._verify_canary(valid_response))
        self.assertFalse(self.agent._verify_canary(invalid_response))

    def test_emergency_prune_history(self):
        self.agent.messages = [
            {"role": "system", "content": "System prompt base con centinela."},
            {"role": "user", "content": "Meta principal del usuario."},
            {"role": "assistant", "content": "Paso 1 intermedio"},
            {"role": "user", "content": "Paso 2 intermedio"},
            {"role": "assistant", "content": "Paso 3 intermedio"},
            {"role": "assistant", "content": "Paso 4 reciente"}
        ]
        self.agent._emergency_prune_history()
        # Debe conservar el system prompt original, la meta del usuario y nota de poda
        self.assertGreaterEqual(len(self.agent.messages), 3)
        self.assertEqual(self.agent.messages[0]["role"], "system")
        self.assertEqual(self.agent.messages[1]["role"], "user")
        self.assertTrue(any("PODA DE EMERGENCIA" in m["content"] for m in self.agent.messages))

    def test_sanitize_final_answer_removes_canary(self):
        raw = "CANARY::JEV_ACTIVE_CTX\nLa tarea ha concluido satisfactoriamente."
        sanitized = self.agent._sanitize_final_answer(raw)
        self.assertNotIn("CANARY::JEV_ACTIVE_CTX", sanitized)
        self.assertIn("La tarea ha concluido satisfactoriamente.", sanitized)


class TestSDLCSeniorProtocol(unittest.TestCase):
    """Pruebas del Protocolo SDLC Senior con checkpoints, red-teaming y cobertura."""

    def setUp(self):
        self.tool = SDLCSeniorTool()

    def test_sdlc_planner_checkpoints(self):
        res = self.tool.execute(
            action="plan_phase",
            task_title="Sistema de Autenticación OAuth2",
            requirements=["Tokens JWT seguros", "Refresh token rotation"]
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["total_checkpoints"], 5)
        self.assertIn("CHK-01-ARCH", [c["id"] for c in res.data["checkpoints"]])
        self.assertIn("CHK-03-SECURITY", [c["id"] for c in res.data["checkpoints"]])
        self.assertTrue(any("CHK-04-TESTS" in c["id"] for c in res.data["checkpoints"]))

    def test_security_auditor_detects_vulnerabilities(self):
        vulnerable_code = """
import sqlite3
import os

def login(user, pwd):
    query = f"SELECT * FROM users WHERE user = '{user}' AND pass = '{pwd}'"
    os.system(f"echo {user}")
    api_key = "AIzaSyD-1234567890abcdef"
    return query
"""
        audit = SDLCSecurityAuditor.audit_code(vulnerable_code)
        self.assertFalse(audit["is_secure"])
        types = [v["type"].upper() for v in audit["vulnerabilities"]]
        self.assertTrue(any("SQL" in t for t in types))
        self.assertTrue(any("COMMAND" in t or "OS" in t for t in types))
        self.assertTrue(any("SECRET" in t or "CREDENTIAL" in t for t in types))

    def test_security_auditor_approves_safe_code(self):
        safe_code = """
import sqlite3
from dataclasses import dataclass

@dataclass(slots=True)
class SafeUser:
    username: str

def safe_login(conn, user: str):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    return cursor.fetchone()
"""
        audit = SDLCSecurityAuditor.audit_code(safe_code)
        self.assertTrue(audit["is_secure"])
        self.assertEqual(len(audit["vulnerabilities"]), 0)

    def test_enforce_testing_coverage(self):
        # Código con funciones
        sample_code = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
"""
        res = self.tool.execute(
            action="enforce_testing",
            code=sample_code,
            min_coverage=80.0
        )
        self.assertIn("coverage_percent", res.data)
        self.assertIn("can_release", res.data)


class TestOSINTToolkit(unittest.TestCase):
    """Pruebas de la suite OSINT en terminal y multi-vector."""

    def setUp(self):
        self.tool = OSINTToolkitTool()

    def test_email_investigation(self):
        # Email institucional / corporativo
        res = self.tool.execute(action="investigate_email", target="security.auditor@proton.me")
        self.assertTrue(res.success)
        self.assertTrue(res.data["is_valid_rfc"])
        self.assertEqual(res.data["domain"], "proton.me")
        self.assertFalse(res.data["is_disposable"])
        self.assertEqual(len(res.data["k_anonymity_prefix"]), 5)

        # Email desechable
        res_disp = self.tool.execute(action="investigate_email", target="temp_user@mailinator.com")
        self.assertTrue(res_disp.data["is_disposable"])
        self.assertLess(res_disp.data["reputation_score"], 80)

    def test_onion_crawler_and_threejs_export(self):
        seed = "expyuz4wqqfdgah56trldsdv24egeq5t6yuhbnjmki87654321qwerty.onion"
        res = self.tool.execute(action="crawl_onion", target=seed, max_depth=2)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.data["total_nodes"], 1)
        self.assertIn("threejs_graph", res.data)
        self.assertEqual(res.data["threejs_graph"]["type"], "onion_network_topology")
        self.assertIn("nodes", res.data["threejs_graph"])

    def test_bssid_analysis_and_distance(self):
        # MAC conocida OUI (Raspberry Pi)
        mac = "DC:A6:32:11:22:33"
        res = self.tool.execute(action="lookup_bssid", target=mac, rssi_dbm=-60)
        self.assertTrue(res.success)
        self.assertIn("Raspberry Pi", res.data["vendor_oui"])
        self.assertGreater(res.data["estimated_distance_meters"], 0.0)

    def test_blockchain_tracer_eth_and_btc(self):
        # Ethereum
        eth_addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        res_eth = self.tool.execute(action="trace_blockchain", target=eth_addr)
        self.assertTrue(res_eth.success)
        self.assertIn("Ethereum", res_eth.data["network"])

        # Bitcoin Bech32
        btc_addr = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
        res_btc = self.tool.execute(action="trace_blockchain", target=btc_addr)
        self.assertTrue(res_btc.success)
        self.assertIn("Bitcoin", res_btc.data["network"])

    def test_telecom_phone_and_asn(self):
        # Teléfono E.164 España
        res_tel = self.tool.execute(action="lookup_phone", target="+34612345678")
        self.assertTrue(res_tel.success)
        self.assertEqual(res_tel.data["country_name"], "España")

        # ASN Google
        res_asn = self.tool.execute(action="lookup_asn", target="15169")
        self.assertTrue(res_asn.success)
        self.assertEqual(res_asn.data["as_name"], "GOOGLE")


class TestWebDesignProEngine(unittest.TestCase):
    """Pruebas del Motor de Diseño Web Anti-Genericidad Pro Max."""

    def setUp(self):
        self.tool = WebDesignProTool(workspace_dir="workspace")

    def test_catalog_contains_68_themes(self):
        res = self.tool.execute(action="list_themes")
        self.assertTrue(res.success)
        self.assertEqual(res.data["total_themes"], 68)

    def test_wcag_contrast_calculation(self):
        # Blanco sobre negro = 21:1
        ratio_max = AntiGenericQualityEngine.calculate_contrast_ratio("#ffffff", "#000000")
        self.assertGreaterEqual(ratio_max, 20.0)

        # Mismo color = 1:1
        ratio_min = AntiGenericQualityEngine.calculate_contrast_ratio("#ffffff", "#ffffff")
        self.assertEqual(ratio_min, 1.0)

    def test_generate_ui_pro_max(self):
        res = self.tool.execute(
            action="generate_ui",
            theme="dark_cyberpunk",
            title="Dashboard de Mando Orbital",
            headline="Telemetría Cuántica en Tiempo Real"
        )
        self.assertTrue(res.success)
        html = res.data["html"]
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("cubic-bezier(0.16, 1, 0.3, 1)", html)
        self.assertIn("--space-8", html)
        self.assertIn("fonts.googleapis.com", html)
        self.assertGreaterEqual(res.data["wcag_ratio"], 4.5)

    def test_anti_generic_audit_catches_poor_design(self):
        generic_boring_html = """
        <html><body>
            <div style="background: #ffffff; border: 1px solid #ccc;">
                <h1>Boring Plain Title</h1>
            </div>
        </body></html>
        """
        audit = AntiGenericQualityEngine.audit_html(generic_boring_html)
        self.assertFalse(audit["is_pro_grade"])
        self.assertLess(audit["anti_generic_score"], 80)


class TestFullRegistryIntegration(unittest.TestCase):
    """Verifica que el ToolRegistry y SkillRegistry expongan todas las capacidades."""

    def test_default_registry_has_master_expansion_tools(self):
        reg, _ = build_default_registry()
        tool_names = [t.name for t in reg.list_tools()]

        self.assertIn("skill_sdlc_senior", tool_names)
        self.assertIn("skill_osint_investigator", tool_names)
        self.assertIn("skill_web_design_pro", tool_names)


if __name__ == "__main__":
    unittest.main()
