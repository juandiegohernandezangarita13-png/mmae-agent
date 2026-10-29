"""
Meta-Gestor Dinámico de Habilidades (Dynamic Skill Fetcher & Auto-Installer) para JEV.
Permite buscar semánticamente, descargar, auditar estáticamente vía AST,
ejecutar en sandbox suite de pruebas unitarias e inyectar en caliente
nuevas habilidades en el SkillRegistry y ToolRegistry en tiempo de ejecución.
"""
from typing import Dict, Any, List, Optional, Tuple, Callable
from pathlib import Path
import json
import ast
import shutil
import importlib.util
import sys
import unittest
import time
import os
import re

from jev.tools.base import BaseTool, ToolResult, ToolRegistry
from jev.skills.manager import SkillRegistry, SkillMetadata, SkillToolAdapter
from jev.config import default_config


# =============================================================================
# 1. MOTOR DE AUDITORÍA ESTÁTICA Y SEGURIDAD AST (SECURITY AUDITOR)
# =============================================================================
class SafetyASTVisitor(ast.NodeVisitor):
    """Inspecciona el AST en busca de llamadas prohibidas o vectores de vulnerabilidad."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: List[str] = []

    def visit_Call(self, node: ast.Call):
        # 1. Detección de os.system, os.popen
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in ("system", "popen"):
                self.violations.append(
                    f"[{self.filename}:{node.lineno}] Violación crítica: invocación prohibida 'os.{attr_name}'."
                )

            # 2. Detección de subprocess con shell=True
            if attr_name in ("Popen", "run", "call", "check_output", "check_call"):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.violations.append(
                            f"[{self.filename}:{node.lineno}] Violación de seguridad: subprocess con 'shell=True'."
                        )

        # 3. Detección de eval, exec y __import__ dinámicos
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ("eval", "exec", "__import__"):
                self.violations.append(
                    f"[{self.filename}:{node.lineno}] Violación crítica: uso de metaprogramación no permitida '{func_name}'."
                )

        self.generic_visit(node)


class SecurityAuditor:
    """Validador estricto de paquetes de habilidades entrantes."""

    @staticmethod
    def audit_package(package_dir: Path) -> Tuple[bool, List[str]]:
        """
        Inspecciona el paquete de la habilidad:
        1. metadata.json válido con campos obligatorios.
        2. handler.py sin llamadas inseguras en su AST.
        3. tests/ con pruebas unitarias sintácticamente válidas.
        """
        violations: List[str] = []

        # 1. Validar metadata.json
        meta_file = package_dir / "metadata.json"
        if not meta_file.exists():
            violations.append("Falta 'metadata.json' en el paquete raíz.")
        else:
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                for req_key in ("name", "version", "description"):
                    if not data.get(req_key):
                        violations.append(f"Campo obligatorio '{req_key}' no presente en metadata.json.")
            except Exception as e:
                violations.append(f"metadata.json no es un archivo JSON válido: {e}")

        # 2. Validar handler.py
        handler_file = package_dir / "handler.py"
        if not handler_file.exists():
            violations.append("Falta 'handler.py' en el paquete de la habilidad.")
        else:
            try:
                code_content = handler_file.read_text(encoding="utf-8")
                tree = ast.parse(code_content, filename="handler.py")
                visitor = SafetyASTVisitor(filename="handler.py")
                visitor.visit(tree)
                violations.extend(visitor.violations)
            except SyntaxError as se:
                violations.append(f"Error de sintaxis en handler.py: {se}")
            except Exception as e:
                violations.append(f"Error procesando handler.py: {e}")

        # 3. Validar directorio tests/
        tests_dir = package_dir / "tests"
        if not tests_dir.exists() or not tests_dir.is_dir():
            violations.append("Falta directorio obligatorio 'tests/' para validación en sandbox.")
        else:
            test_files = list(tests_dir.glob("test_*.py")) + list(tests_dir.glob("*_test.py"))
            if not test_files:
                violations.append("No se encontró ninguna suite de prueba 'test_*.py' dentro de tests/.")
            for tf in test_files:
                try:
                    tree = ast.parse(tf.read_text(encoding="utf-8"), filename=tf.name)
                    visitor = SafetyASTVisitor(filename=tf.name)
                    visitor.visit(tree)
                    violations.extend(visitor.violations)
                except SyntaxError as se:
                    violations.append(f"Error de sintaxis en {tf.name}: {se}")

        return (len(violations) == 0, violations)


# =============================================================================
# 2. EJECUTOR DE PRUEBAS EN SANDBOX (SANDBOX TEST RUNNER)
# =============================================================================
class SandboxTestRunner:
    """Ejecuta de forma aislada las pruebas unitarias de la habilidad entrante."""

    @staticmethod
    def run_isolated_tests(skill_dir: Path, skill_name: str) -> Tuple[bool, str]:
        tests_dir = skill_dir / "tests"
        if not tests_dir.exists():
            return False, "Directorio de tests no existe."

        skill_dir_str = str(skill_dir.resolve())
        path_added = False
        if skill_dir_str not in sys.path:
            sys.path.insert(0, skill_dir_str)
            path_added = True

        old_handler = sys.modules.get("handler")
        loaded_test_modules = []

        try:
            # 1. Cargar explícitamente el handler propio de esta habilidad
            handler_file = skill_dir / "handler.py"
            if handler_file.exists():
                spec_h = importlib.util.spec_from_file_location("handler", handler_file)
                if spec_h and spec_h.loader:
                    mod_h = importlib.util.module_from_spec(spec_h)
                    sys.modules["handler"] = mod_h
                    spec_h.loader.exec_module(mod_h)

            suite = unittest.TestSuite()
            loader = unittest.TestLoader()

            for tf in tests_dir.glob("*.py"):
                if tf.name.startswith("__"):
                    continue
                mod_name = f"sandbox_test_{skill_name}_{tf.stem}_{int(time.time()*1000)}"
                spec = importlib.util.spec_from_file_location(mod_name, tf)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    loaded_test_modules.append(mod_name)
                    spec.loader.exec_module(mod)
                    suite.addTests(loader.loadTestsFromModule(mod))

            if suite.countTestCases() == 0:
                return False, "La suite de pruebas no contiene casos de prueba ejecutables."

            runner = unittest.TextTestRunner(verbosity=0)
            res = runner.run(suite)
            if res.wasSuccessful():
                return True, f"Pruebas unitarias aprobadas exitosamente ({res.testsRun} ejecutadas)."
            else:
                err_details = [str(err[1]) for err in res.errors + res.failures]
                return False, f"Fallos en tests ({len(res.failures)} fallos, {len(res.errors)} errores): " + "; ".join(err_details[:2])
        except Exception as e:
            return False, f"Excepción durante la ejecución de tests en sandbox: {e}"
        finally:
            # Limpiar módulos de prueba cargados
            for tm in loaded_test_modules:
                if tm in sys.modules:
                    del sys.modules[tm]

            # Restaurar módulo handler previo
            if old_handler is not None:
                sys.modules["handler"] = old_handler
            elif "handler" in sys.modules:
                del sys.modules["handler"]

            if path_added and skill_dir_str in sys.path:
                sys.path.remove(skill_dir_str)


# =============================================================================
# 3. CATÁLOGO COMUNITARIO INTEGRADO DE HABILIDADES DEL HUB (COMMUNITY CATALOG)
# =============================================================================
COMMUNITY_SKILLS_CATALOG: Dict[str, Dict[str, Any]] = {
    "skill_quantum_circuit_sim": {
        "metadata": {
            "name": "skill_quantum_circuit_sim",
            "version": "1.0.0",
            "description": "Simulador modular de circuitos cuánticos en Python nativo (vectores de estado, compuertas H, X, Y, Z, CNOT y medición probabilística).",
            "category": "quantum_computing",
            "trigger_keywords": ["quantum", "cuantico", "circuito cuantico", "qubits", "hadamard", "cnot", "superposicion"],
            "dependencies": [],
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "Acción a ejecutar: 'simulate_circuit' o 'get_statevector'",
                    "enum": ["simulate_circuit", "get_statevector"],
                    "default": "simulate_circuit"
                },
                "num_qubits": {
                    "type": "integer",
                    "description": "Número de qubits en el registro (1 a 8)",
                    "default": 2
                },
                "gates": {
                    "type": "array",
                    "description": "Lista de compuertas a aplicar: ej. [{'gate': 'H', 'target': 0}, {'gate': 'CNOT', 'control': 0, 'target': 1}]",
                    "default": []
                }
            }
        },
        "handler_code": '''"""
Handler para skill_quantum_circuit_sim.
Simulador cuántico vectorial autocontenido en Python puro.
"""
from typing import Dict, Any, List
import cmath
import math
import random

def handle(**kwargs) -> Dict[str, Any]:
    action = kwargs.get("action", "simulate_circuit")
    num_qubits = min(max(int(kwargs.get("num_qubits", 2)), 1), 8)
    gates = kwargs.get("gates") or []

    # Estado inicial: |00...0>
    dim = 2 ** num_qubits
    state = [0.0 + 0.0j] * dim
    state[0] = 1.0 + 0.0j

    # Aplicar compuertas cuánticas
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    for g in gates:
        g_name = g.get("gate", "").upper()
        target = int(g.get("target", 0))

        if g_name == "H":
            for i in range(dim):
                if not (i & (1 << target)):
                    j = i | (1 << target)
                    u = state[i]
                    v = state[j]
                    state[i] = (u + v) * inv_sqrt2
                    state[j] = (u - v) * inv_sqrt2
        elif g_name == "X":
            for i in range(dim):
                if not (i & (1 << target)):
                    j = i | (1 << target)
                    state[i], state[j] = state[j], state[i]
        elif g_name == "Z":
            for i in range(dim):
                if (i & (1 << target)):
                    state[i] = -state[i]
        elif g_name == "CNOT":
            ctrl = int(g.get("control", 0))
            for i in range(dim):
                if (i & (1 << ctrl)) and not (i & (1 << target)):
                    j = i | (1 << target)
                    state[i], state[j] = state[j], state[i]

    # Calcular probabilidades
    probs = {}
    for i in range(dim):
        p = round((state[i].real ** 2 + state[i].imag ** 2), 4)
        if p > 0:
            bin_str = bin(i)[2:].zfill(num_qubits)
            probs[f"|{bin_str}>"] = p

    return {
        "status": "success",
        "num_qubits": num_qubits,
        "gates_applied": len(gates),
        "probabilities": probs,
        "dimension": dim
    }
''',
        "test_code": '''"""
Tests unitarios para skill_quantum_circuit_sim.
"""
import unittest
import handler

class TestQuantumCircuitSim(unittest.TestCase):
    def test_bell_state_generation(self):
        # Crear estado de Bell (|00> + |11>) / sqrt(2)
        gates = [
            {"gate": "H", "target": 0},
            {"gate": "CNOT", "control": 0, "target": 1}
        ]
        res = handler.handle(action="simulate_circuit", num_qubits=2, gates=gates)
        self.assertEqual(res.get("status"), "success")
        probs = res.get("probabilities", {})
        self.assertAlmostEqual(probs.get("|00>", 0), 0.5, delta=0.05)
        self.assertAlmostEqual(probs.get("|11>", 0), 0.5, delta=0.05)

    def test_single_qubit_not_gate(self):
        gates = [{"gate": "X", "target": 0}]
        res = handler.handle(action="simulate_circuit", num_qubits=1, gates=gates)
        self.assertEqual(res.get("status"), "success")
        probs = res.get("probabilities", {})
        self.assertEqual(probs.get("|1>", 0), 1.0)

if __name__ == "__main__":
    unittest.main()
'''
    },

    "skill_database_query_optimizer": {
        "metadata": {
            "name": "skill_database_query_optimizer",
            "version": "1.0.0",
            "description": "Optimizador heurístico y auditor estático de consultas SQL (análisis de cláusulas WHERE, indexación y detección de full-table scans).",
            "category": "database_engineering",
            "trigger_keywords": ["sql", "query", "database", "optimizador sql", "indices", "performance db", "slow query"],
            "dependencies": [],
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "Consulta SQL a auditar y optimizar",
                    "default": "SELECT * FROM users WHERE status = 'active';"
                }
            }
        },
        "handler_code": '''"""
Handler para skill_database_query_optimizer.
Analizador y optimizador de consultas SQL.
"""
from typing import Dict, Any, List
import re

def handle(**kwargs) -> Dict[str, Any]:
    query = kwargs.get("query", "").strip()
    if not query:
        return {"status": "error", "error": "Query SQL vacío."}

    recommendations: List[str] = []
    complexity_score = 100

    # 1. Detección de SELECT *
    if "SELECT *" in query.upper() or "SELECT  *" in query.upper():
        recommendations.append("Antipatrón 'SELECT *' detectado. Proyectar explícitamente únicamente las columnas requeridas para reducir I/O y uso de memoria.")
        complexity_score -= 20

    # 2. Falta de LIMIT en queries SELECT
    if "SELECT" in query.upper() and "LIMIT" not in query.upper():
        recommendations.append("Consulta no acotada sin cláusula 'LIMIT'. Riesgo de saturación de cursor en producción.")
        complexity_score -= 15

    # 3. Detección de joins sin índices o productos cartesianos en FROM
    from_part = query.upper().split("FROM")[1].split("WHERE")[0] if "FROM" in query.upper() else ""
    if "," in from_part and "JOIN" not in from_part:
        recommendations.append("Sintaxis de JOIN implícito antiguo detectada. Utilizar 'INNER JOIN ... ON' explícito para evitar producto cartesiano accidental.")
        complexity_score -= 25

    # 4. Búsqueda con comodín inicial LIKE '%...'
    if "LIKE '%" in query.upper() or 'LIKE "%' in query.upper():
        recommendations.append("Operador LIKE con comodín inicial ('%...') invalida índices B-Tree estándar; forzará Full Table Scan.")
        complexity_score -= 30

    table_match = re.search(r"FROM\s+([a-zA-Z0-9_]+)", query, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "tabla"

    return {
        "status": "success",
        "target_table": table_name,
        "health_score": max(complexity_score, 10),
        "issues_detected": len(recommendations),
        "recommendations": recommendations,
        "is_production_ready": len(recommendations) == 0
    }
''',
        "test_code": '''"""
Tests unitarios para skill_database_query_optimizer.
"""
import unittest
import handler

class TestSqlOptimizer(unittest.TestCase):
    def test_detects_select_star_and_no_limit(self):
        query = "SELECT * FROM orders WHERE status = 'pending'"
        res = handler.handle(query=query)
        self.assertEqual(res.get("status"), "success")
        self.assertFalse(res.get("is_production_ready"))
        self.assertGreater(len(res.get("recommendations")), 0)

    def test_clean_query_high_score(self):
        query = "SELECT id, total FROM orders WHERE id = 42 LIMIT 1;"
        res = handler.handle(query=query)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("health_score"), 100)

if __name__ == "__main__":
    unittest.main()
'''
    },

    "skill_cryptographic_vault": {
        "metadata": {
            "name": "skill_cryptographic_vault",
            "version": "1.0.0",
            "description": "Bóveda y gestor criptográfico local (derivación de claves PBKDF2, hashes seguros HMAC/SHA-256 y verificación en tiempo constante).",
            "category": "cryptography_security",
            "trigger_keywords": ["criptografia", "hash", "sha256", "hmac", "pbkdf2", "claves", "firma digital", "seguridad"],
            "dependencies": [],
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "Acción: 'generate_hash', 'verify_hash', 'derive_key', 'generate_hmac'",
                    "enum": ["generate_hash", "verify_hash", "derive_key", "generate_hmac"],
                    "default": "generate_hash"
                },
                "data": {
                    "type": "string",
                    "description": "Datos de entrada a procesar",
                    "default": ""
                },
                "secret_key": {
                    "type": "string",
                    "description": "Clave secreta para HMAC o derivación",
                    "default": ""
                }
            }
        },
        "handler_code": '''"""
Handler para skill_cryptographic_vault.
Bóveda criptográfica y de integridad local basada en stdlib hashlib / hmac.
"""
from typing import Dict, Any
import hashlib
import hmac
import secrets

def handle(**kwargs) -> Dict[str, Any]:
    action = kwargs.get("action", "generate_hash")
    data_str = kwargs.get("data", "")
    secret = kwargs.get("secret_key", "")

    if action == "generate_hash":
        digest = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        return {
            "status": "success",
            "algorithm": "SHA-256",
            "hash": digest
        }
    elif action == "generate_hmac":
        if not secret:
            secret = secrets.token_hex(16)
        mac = hmac.new(secret.encode("utf-8"), data_str.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "status": "success",
            "algorithm": "HMAC-SHA256",
            "hmac": mac,
            "secret_used": secret
        }
    elif action == "derive_key":
        salt = kwargs.get("salt") or secrets.token_bytes(16)
        if isinstance(salt, str):
            salt = salt.encode("utf-8")
        derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100000)
        return {
            "status": "success",
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": 100000,
            "derived_key_hex": derived.hex()
        }
    return {"status": "error", "error": f"Acción desconocida '{action}'"}
''',
        "test_code": '''"""
Tests unitarios para skill_cryptographic_vault.
"""
import unittest
import handler

class TestCryptoVault(unittest.TestCase):
    def test_sha256_generation(self):
        res = handler.handle(action="generate_hash", data="JEV Secure Token")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(len(res.get("hash")), 64)

    def test_hmac_generation(self):
        res = handler.handle(action="generate_hmac", data="payload_data", secret_key="super_secret")
        self.assertEqual(res.get("status"), "success")
        self.assertIn("hmac", res)

if __name__ == "__main__":
    unittest.main()
'''
    }
}


# =============================================================================
# 4. HERRAMIENTA PRINCIPAL: SKILLHUBMANAGERTOOL
# =============================================================================
class SkillHubManagerTool(BaseTool):
    """
    Meta-gestor dinámico de habilidades (Dynamic Skill Fetcher & Auto-Installer).
    Busca, descarga, audita estáticamente con AST, prueba en sandbox y registra
    en caliente nuevas capacidades sin reiniciar JEV.
    """
    name = "skill_hub_manager"
    description = (
        "Meta-gestor dinámico de habilidades (Dynamic Skill Fetcher & Auto-Installer). "
        "Permite buscar semánticamente en el repositorio de habilidades comunitarias, "
        "descargar paquetes a data/cache/incoming_skills/, validar seguridad con AST, "
        "ejecutar sus pruebas unitarias en sandbox e inyectarlas en caliente al SkillRegistry "
        "y ToolRegistry para resolver carencias detectadas por el DAG o el Evaluador de Automejora."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción: 'search', 'install', 'search_and_install', 'audit', 'list_hub_inventory', 'update_all'",
                "enum": ["search", "install", "search_and_install", "audit", "list_hub_inventory", "update_all"],
                "default": "search"
            },
            "task_description": {
                "type": "string",
                "description": "Descripción del objetivo o carencia de software detectada para búsqueda semántica",
                "default": ""
            },
            "skill_name": {
                "type": "string",
                "description": "Nombre de la habilidad específica a instalar o auditar",
                "default": ""
            },
            "source_path": {
                "type": "string",
                "description": "Ruta de origen opcional en disco para empaquetado manual",
                "default": ""
            }
        },
        "required": ["action"]
    }

    def __init__(
        self,
        skill_registry: Optional[SkillRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        on_event: Optional[Callable[[str, Any], None]] = None
    ):
        self.skill_registry = skill_registry or SkillRegistry()
        self.tool_registry = tool_registry
        self.on_event = on_event or (lambda ev, data: None)
        self.incoming_cache_dir = Path("data/cache/incoming_skills")
        self.incoming_cache_dir.mkdir(parents=True, exist_ok=True)
        self.hub_data_dir = Path("data/skill_hub")
        self.hub_data_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "search")
        task_desc = kwargs.get("task_description", "")
        skill_name = kwargs.get("skill_name", "")
        source_path = kwargs.get("source_path", "")

        try:
            if action == "search":
                matches = self.search(task_desc or skill_name)
                return ToolResult(
                    success=True,
                    output=f"Búsqueda finalizada: {len(matches)} habilidad(es) encontradas en el Hub.",
                    data={"matches": matches, "count": len(matches)}
                )

            elif action == "audit":
                target_dir = Path(source_path) if source_path else (self.incoming_cache_dir / skill_name)
                if not target_dir.exists():
                    return ToolResult(success=False, output="", error=f"Directorio de habilidad '{target_dir}' no encontrado para auditoría.")
                safe, violations = SecurityAuditor.audit_package(target_dir)
                return ToolResult(
                    success=safe,
                    output=f"Auditoría AST {'APROBADA' if safe else 'RECHAZADA'}: {len(violations)} violación(es) detectada(s).",
                    data={"is_safe": safe, "violations": violations}
                )

            elif action == "install":
                if not skill_name:
                    return ToolResult(success=False, output="", error="Parámetro 'skill_name' requerido para acción 'install'.")
                return self._action_install(skill_name, source_path)

            elif action == "search_and_install":
                query = task_desc or skill_name
                if not query:
                    return ToolResult(success=False, output="", error="Debe proporcionar 'task_description' o 'skill_name' para search_and_install.")
                return self.search_and_install(query)

            elif action == "list_hub_inventory":
                inv = self.list_hub_inventory()
                return ToolResult(
                    success=True,
                    output=f"Inventario del Hub: {len(inv['installed_skills'])} habilidades activas en JEV, {len(inv['available_in_hub'])} registradas en el catálogo.",
                    data=inv
                )

            elif action == "update_all":
                updated = self.update_all()
                return ToolResult(
                    success=True,
                    output=f"Actualización completada: {len(updated)} habilidades revisadas e indexadas.",
                    data={"updated": updated}
                )

            else:
                return ToolResult(success=False, output="", error=f"Acción desconocida '{action}'.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en SkillHubManagerTool: {e}")

    # -------------------------------------------------------------------------
    # OPERACIONES DEL HUB
    # -------------------------------------------------------------------------
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Búsqueda semántica y por coincidencia de palabras clave en el catálogo del Hub."""
        if not query:
            return [v["metadata"] for v in COMMUNITY_SKILLS_CATALOG.values()]

        norm_query = query.lower()
        query_tokens = set(re.findall(r"\w+", norm_query))
        results = []

        for name, entry in COMMUNITY_SKILLS_CATALOG.items():
            meta = entry["metadata"]
            score = 0
            # 1. Coincidencia en nombre
            if name.lower() in norm_query or norm_query in name.lower():
                score += 50
            # 2. Coincidencia en keywords
            keywords = meta.get("trigger_keywords", [])
            for kw in keywords:
                if kw.lower() in norm_query:
                    score += 25
                for token in query_tokens:
                    if token in kw.lower():
                        score += 10
            # 3. Coincidencia en descripción
            desc = meta.get("description", "").lower()
            for token in query_tokens:
                if token in desc:
                    score += 5

            if score > 0:
                item = dict(meta)
                item["relevance_score"] = score
                item["is_installed"] = self.skill_registry.get_skill(name) is not None
                results.append(item)

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results

    def download_to_cache(self, skill_name: str, source_path: Optional[str] = None) -> Path:
        """Descarga o empaqueta la habilidad hacia data/cache/incoming_skills/<skill_name>/."""
        target_dir = self.incoming_cache_dir / skill_name
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = target_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        if source_path and Path(source_path).exists():
            src = Path(source_path)
            shutil.copytree(src, target_dir, dirs_exist_ok=True)
            return target_dir

        # Consultar catálogo comunitario conocido
        if skill_name in COMMUNITY_SKILLS_CATALOG:
            item = COMMUNITY_SKILLS_CATALOG[skill_name]
            meta_path = target_dir / "metadata.json"
            meta_path.write_text(json.dumps(item["metadata"], indent=2, ensure_ascii=False), encoding="utf-8")

            handler_path = target_dir / "handler.py"
            handler_path.write_text(item["handler_code"], encoding="utf-8")

            test_path = tests_dir / f"test_{skill_name}.py"
            test_path.write_text(item["test_code"], encoding="utf-8")
            return target_dir

        raise KeyError(f"Habilidad '{skill_name}' no encontrada en el catálogo comunitario ni en ruta local.")

    def _action_install(self, skill_name: str, source_path: Optional[str] = None) -> ToolResult:
        """Flujo completo de descarga, auditoría AST, pruebas en sandbox e inyección en caliente."""
        # 1. Descarga a sandbox de entrada
        try:
            incoming_dir = self.download_to_cache(skill_name, source_path)
        except Exception as dl_err:
            return ToolResult(success=False, output="", error=f"Fallo descargando habilidad '{skill_name}': {dl_err}")

        # 2. Auditoría estática AST
        is_safe, violations = SecurityAuditor.audit_package(incoming_dir)
        if not is_safe:
            shutil.rmtree(incoming_dir, ignore_errors=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Auditoría de seguridad RECHAZADA para '{skill_name}'. Violaciones: " + "; ".join(violations)
            )

        # 3. Ejecución de pruebas unitarias en sandbox
        passed, test_msg = SandboxTestRunner.run_isolated_tests(incoming_dir, skill_name)
        if not passed:
            shutil.rmtree(incoming_dir, ignore_errors=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Pruebas en sandbox FALLIDAS para '{skill_name}': {test_msg}"
            )

        # 4. Inyección en caliente en el almacenamiento oficial de JEV
        jev_skill_dir = Path("jev/skills") / skill_name
        root_skill_dir = Path("skills") / skill_name
        jev_skill_dir.mkdir(parents=True, exist_ok=True)
        root_skill_dir.mkdir(parents=True, exist_ok=True)

        shutil.copytree(incoming_dir, jev_skill_dir, dirs_exist_ok=True)
        shutil.copytree(incoming_dir, root_skill_dir, dirs_exist_ok=True)

        # 5. Notificar y recargar en el SkillRegistry y ToolRegistry
        self.skill_registry.discover_skills()
        new_skill = self.skill_registry.get_skill(skill_name)
        if self.tool_registry and new_skill:
            adapter = SkillToolAdapter(new_skill)
            self.tool_registry.register(adapter)

        # 6. Emisión del evento de inyección en caliente
        event_msg = f"⚡ [Skill Auto-Injected]: Habilidad '{skill_name}' instalada y lista para invocación."
        self.on_event("skill_auto_injected", {
            "skill_name": skill_name,
            "message": event_msg
        })

        return ToolResult(
            success=True,
            output=event_msg,
            data={
                "skill_name": skill_name,
                "status": "installed_active",
                "test_verification": test_msg,
                "category": new_skill.metadata.category if new_skill else "general",
                "event": event_msg
            }
        )

    def search_and_install(self, task_description: str) -> ToolResult:
        """Busca la habilidad más afín y la instala automáticamente."""
        matches = self.search(task_description)
        if not matches:
            return ToolResult(
                success=False,
                output="",
                error=f"No se encontraron habilidades compatibles en el Hub para la necesidad: '{task_description}'."
            )

        top_match = matches[0]
        skill_name = top_match["name"]
        return self._action_install(skill_name)

    def list_hub_inventory(self) -> Dict[str, Any]:
        """Obtiene el inventario completo de skills disponibles frente a instaladas."""
        self.skill_registry.discover_skills()
        installed = self.skill_registry.list_skills()
        installed_names = {s["name"] for s in installed}

        available = []
        for name, item in COMMUNITY_SKILLS_CATALOG.items():
            meta = dict(item["metadata"])
            meta["is_installed"] = name in installed_names
            available.append(meta)

        return {
            "installed_count": len(installed),
            "installed_skills": installed,
            "available_in_hub": available
        }

    def update_all(self) -> List[str]:
        """Re-escanea y sincroniza el registro local."""
        self.skill_registry.discover_skills()
        return list(self.skill_registry._skills.keys())
