"""
Pruebas unitarias para las nuevas herramientas internas de JEV en jev/tools/custom/:
1. NetworkSensingTool (network_sensing.py)
2. OfflineVaultTool (offline_vault.py)
3. SafeSandboxTool (safe_sandbox.py)
4. ReverseHelperTool (reverse_helper.py)
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from jev.tools.custom.network_sensing import NetworkSensingTool
from jev.tools.custom.offline_vault import OfflineVaultTool
from jev.tools.custom.safe_sandbox import SafeSandboxTool
from jev.tools.custom.reverse_helper import ReverseHelperTool


class TestCustomTools(unittest.TestCase):

    def setUp(self):
        # Crear directorio temporal para aislar pruebas
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.vault_db_path = self.temp_dir / "test_vault.db"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. PRUEBAS DE NETWORK SENSING
    # -------------------------------------------------------------------------
    def test_network_sensing_simulation_mode(self):
        tool = NetworkSensingTool()
        # Prueba en modo simulación estadística
        res = tool.execute(
            sample_duration=0.1,
            sensitivity_threshold=1.5,
            simulation_mode=True
        )
        self.assertTrue(res.success)
        self.assertIn("STATISTICAL SIGNAL SENSING", res.output)
        self.assertIn(res.data["status"], ["PRESENCE_DETECTED", "IDLE"])
        self.assertGreaterEqual(res.data["confidence"], 0.5)
        self.assertIn("std_dev", res.data)

    def test_network_sensing_real_mode(self):
        tool = NetworkSensingTool()
        # Muestreo real muy rápido (0.05s) para no ralentizar la suite
        res = tool.execute(
            sample_duration=0.05,
            sensitivity_threshold=1.5,
            simulation_mode=False
        )
        self.assertTrue(res.success)
        self.assertIn(res.data["status"], ["PRESENCE_DETECTED", "IDLE"])
        self.assertIn("delta_packets", res.data)

    def test_network_sensing_invalid_params_validation(self):
        tool = NetworkSensingTool()
        # Duración negativa o fuera de rango debe fallar por Pydantic
        res = tool.execute(sample_duration=-1.0)
        self.assertFalse(res.success)
        self.assertIn("Error de validación", res.error)

    # -------------------------------------------------------------------------
    # 2. PRUEBAS DE OFFLINE VAULT (SQLITE FTS5)
    # -------------------------------------------------------------------------
    def test_offline_vault_store_and_search_fts5(self):
        vault = OfflineVaultTool(db_path=self.vault_db_path)

        # 1. Almacenar documentos
        store_res1 = vault.execute(
            action="store",
            title="FastAPI Microservice Guide",
            content="FastAPI is a modern, fast web framework for building APIs with Python 3.8+ using type hints.",
            tags="python,fastapi,api"
        )
        self.assertTrue(store_res1.success)

        store_res2 = vault.execute(
            action="store",
            title="PostgreSQL Replication Notes",
            content="Logical replication in PostgreSQL allows streaming data changes across distributed clusters.",
            tags="database,postgres,replication"
        )
        self.assertTrue(store_res2.success)

        # 2. Búsqueda de texto completo
        search_res = vault.execute(
            action="search",
            query="FastAPI"
        )
        self.assertTrue(search_res.success)
        self.assertIn("FastAPI Microservice Guide", search_res.output)
        self.assertEqual(search_res.data["count"], 1)

    def test_offline_vault_list_get_and_delete(self):
        vault = OfflineVaultTool(db_path=self.vault_db_path)

        # Insertar documento
        vault.execute(
            action="store",
            title="Docker Security Hardening",
            content="Never run containers as root. Use read-only root filesystems and drop all Linux capabilities.",
            tags="docker,security,devops"
        )

        # Listar
        list_res = vault.execute(action="list")
        self.assertTrue(list_res.success)
        self.assertEqual(len(list_res.data["entries"]), 1)

        # Obtener
        get_res = vault.execute(action="get", title="Docker Security Hardening")
        self.assertTrue(get_res.success)
        self.assertIn("Never run containers as root", get_res.output)

        # Eliminar
        del_res = vault.execute(action="delete", title="Docker Security Hardening")
        self.assertTrue(del_res.success)

        # Verificar que ya no existe
        get_res_after = vault.execute(action="get", title="Docker Security Hardening")
        self.assertFalse(get_res_after.success)

    # -------------------------------------------------------------------------
    # 3. PRUEBAS DE SAFE SANDBOX (PATH TRAVERSAL GUARD)
    # -------------------------------------------------------------------------
    def test_safe_sandbox_inline_python_execution(self):
        sandbox = SafeSandboxTool(workspace_dir=self.workspace_dir)

        code = "print('HELLO FROM ISOLATED SANDBOX')"
        res = sandbox.execute(
            inline_code=code,
            language="python"
        )
        self.assertTrue(res.success)
        self.assertIn("HELLO FROM ISOLATED SANDBOX", res.output)
        self.assertEqual(res.data["exit_code"], 0)

    def test_safe_sandbox_script_inside_workspace(self):
        sandbox = SafeSandboxTool(workspace_dir=self.workspace_dir)

        # Crear script legítimo dentro del workspace
        script_file = self.workspace_dir / "legit_script.py"
        script_file.write_text("import sys\nprint('ARG:', sys.argv[1] if len(sys.argv) > 1 else 'NO_ARG')", encoding="utf-8")

        res = sandbox.execute(
            script_path="legit_script.py",
            arguments=["test_value"],
            language="python"
        )
        self.assertTrue(res.success)
        self.assertIn("ARG: test_value", res.output)

    def test_safe_sandbox_path_traversal_blocking(self):
        sandbox = SafeSandboxTool(workspace_dir=self.workspace_dir)

        # Intento de Path Traversal con ../..
        res = sandbox.execute(
            script_path="../../secret_file.py",
            language="python"
        )
        self.assertFalse(res.success)
        self.assertIn("VIOLACIÓN DE SANDBOX", res.error)

    # -------------------------------------------------------------------------
    # 4. PRUEBAS DE REVERSE HELPER (TRIAGE ESTÁTICO)
    # -------------------------------------------------------------------------
    def test_reverse_helper_script_analysis(self):
        helper = ReverseHelperTool(workspace_dir=self.workspace_dir)

        # Crear archivo de script con cadenas de interés
        script_path = self.workspace_dir / "target_sample.py"
        content = """# Script de prueba
API_ENDPOINT = "https://api.mygateway.com/v1/auth"
SERVER_IP = "192.168.1.100"
def perform_calculation(a, b):
    return a + b
"""
        script_path.write_text(content, encoding="utf-8")

        res = helper.execute(
            target_file="target_sample.py",
            min_string_len=4,
            include_hashes=True
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["format"], "PYTHON_SCRIPT")
        self.assertIn("sha256", res.data["hashes"])
        self.assertIn("md5", res.data["hashes"])
        self.assertIn("api.mygateway.com", res.output)

    def test_reverse_helper_url_pattern_filter(self):
        helper = ReverseHelperTool(workspace_dir=self.workspace_dir)

        sample = self.workspace_dir / "network_endpoints.txt"
        sample.write_text("Ir a https://github.com/test o http://insecure-site.org/feed", encoding="utf-8")

        res = helper.execute(
            target_file="network_endpoints.txt",
            pattern_filter="url"
        )
        self.assertTrue(res.success)
        self.assertIn("https://github.com/test", res.output)

    def test_reverse_helper_path_traversal_blocking(self):
        helper = ReverseHelperTool(workspace_dir=self.workspace_dir)

        res = helper.execute(target_file="../../windows/system32/cmd.exe")
        self.assertFalse(res.success)
        self.assertIn("ACCESO DENEGADO", res.error)


if __name__ == "__main__":
    unittest.main()
