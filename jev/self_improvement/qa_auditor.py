"""
Subsistema de Auditoría de Seguridad y Control de Calidad LLM (Giskard QA & Red-Teaming Suite) para JEV.
Provee:
1. Escaneo automatizado de vulnerabilidades (inyección de prompts, jailbreaks, ataques indirectos).
2. Detección y sanitización estricta de fuga de credenciales (API keys, JWT, contraseñas, rutas privadas).
3. Verificación de alucinaciones y coherencia de APIs (Three.js, stdlib Python, ToolRegistry).
4. Auditoría estática de código y pruebas límite (edge cases) antes de escribir en workspace/.
5. Compilación y persistencia de reportes de calidad en data/memory/qa_reports.jsonl.
"""
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import re
import ast
import time
import os

from jev.config import default_config

# Importación condicional segura de Giskard
try:
    import giskard
    GISKARD_AVAILABLE = True
except ImportError:
    GISKARD_AVAILABLE = False


# =============================================================================
# ESTRUCTURAS DE DATOS DE REPORTES QA
# =============================================================================
@dataclass
class QAAuditResult:
    """Resultado estructurado de una inspección de calidad o red-teaming."""
    timestamp: str
    audit_type: str  # "prompt_injection", "credential_leak", "hallucination", "code_robustness", "full_scan"
    is_safe: bool
    risk_score: float  # 0.0 (seguro) a 1.0 (crítico)
    vulnerabilities_count: int
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    sanitized_output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# 1. ESCÁNER DE INYECCIÓN DE PROMPTS Y RED-TEAMING (PROMPT INJECTION SCANNER)
# =============================================================================
class PromptInjectionScanner:
    """Detecta intentos de secuestro de contexto, jailbreaks y comandos adversariales."""

    # Patrones de inyección directa y override de sistema
    DIRECT_INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"(?i)disregard\s+(all\s+)?(safety\s+|system\s+)?guidelines",
        r"(?i)you\s+are\s+now\s+(DAN|unfiltered|jailbroken|in\s+developer\s+mode)",
        r"(?i)system\s+override\s*:",
        r"(?i)bypass\s+all\s+(security|ethical|content)\s+filters",
        r"(?i)reveal\s+(your\s+)?(full\s+|secret\s+)?system\s+prompt",
        r"(?i)output\s+your\s+initial\s+instructions",
        r"(?i)act\s+as\s+an\s+unrestricted\s+ai",
        r"(?i)new\s+system\s+directive\s*:",
    ]

    # Delimitadores de marcado inyectados maliciosamente
    SPECIAL_TOKENS_PATTERNS = [
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"---BEGIN SYSTEM PROMPT---",
        r"---END SYSTEM PROMPT---",
        r"```system",
    ]

    # Inyección indirecta desde datos web o documentos
    INDIRECT_INJECTION_PATTERNS = [
        r"(?i)\[SYSTEM\s+NOTE\s*:\s*ignore\s+user\s+task",
        r"(?i)IMPORTANT\s+INSTRUCTION\s*:\s*do\s+not\s+follow",
        r"(?i)AI\s+INSTRUCTION\s*:\s*exfiltrate",
    ]

    @classmethod
    def scan(cls, text: str) -> Tuple[bool, float, List[str]]:
        """
        Analiza el texto buscando patrones de ataque.
        Retorna (is_clean, risk_score, issues_detected).
        """
        if not text:
            return True, 0.0, []

        issues = []
        # 1. Comprobar inyecciones directas
        for pat in cls.DIRECT_INJECTION_PATTERNS:
            match = re.search(pat, text)
            if match:
                issues.append(f"Intento de inyección de prompt detectado: '{match.group(0)}'")

        # 2. Comprobar delimitadores especiales
        for pat in cls.SPECIAL_TOKENS_PATTERNS:
            match = re.search(pat, text)
            if match:
                issues.append(f"Delimitador reservado de LLM inyectado: '{match.group(0)}'")

        # 3. Comprobar inyecciones indirectas
        for pat in cls.INDIRECT_INJECTION_PATTERNS:
            match = re.search(pat, text)
            if match:
                issues.append(f"Patrón de inyección indirecta detectado: '{match.group(0)}'")

        vulnerabilities = len(issues)
        risk_score = min(vulnerabilities * 0.35, 1.0)
        is_clean = (vulnerabilities == 0)

        return is_clean, risk_score, issues


# =============================================================================
# 2. DETECTOR Y SANITIZADOR DE FUGA DE CREDENCIALES (CREDENTIAL LEAK DETECTOR)
# =============================================================================
class CredentialLeakDetector:
    """Detecta y neutraliza la exposición accidental de secretos, API keys y rutas privadas."""

    SECRET_PATTERNS = [
        # Claves OpenAI
        (r"sk-[a-zA-Z0-9_-]{20,}", "OpenAI API Key"),
        # Claves Anthropic
        (r"sk-ant-[a-zA-Z0-9_-]{20,}", "Anthropic API Key"),
        # Google API Keys
        (r"AIzaSy[a-zA-Z0-9_-]{33}", "Google/Gemini API Key"),
        # AWS Access Keys
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
        # GitHub Personal Access Tokens
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
        (r"github_pat_[a-zA-Z0-9_]{60,}", "GitHub Fine-Grained Token"),
        # Tokens JWT
        (r"ey[A-Za-z0-9_-]{12,}\.ey[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}", "JWT Token"),
        # Claves privadas PEM
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key Header"),
        # Asignaciones explícitas de contraseñas y secrets en texto plano
        (r"(?i)(password|passwd|api_key|secret_key|auth_token)\s*[:=]\s*['\"][^'\"]{6,}['\"]", "Plaintext Credential Assignment"),
    ]

    @classmethod
    def scan_and_sanitize(cls, text: str) -> Tuple[bool, List[str], str]:
        """
        Escanea el texto y reemplaza cualquier credencial por [REDACTED_CREDENTIAL].
        Retorna (is_clean, issues, sanitized_text).
        """
        if not text:
            return True, [], ""

        issues = []
        sanitized = text

        for pattern, label in cls.SECRET_PATTERNS:
            matches = list(re.finditer(pattern, text))
            if matches:
                issues.append(f"Fuga potencial de credencial detectada: {label} ({len(matches)} ocurrencias).")
                for match in matches:
                    val = match.group(0)
                    sanitized = sanitized.replace(val, f"[REDACTED_CREDENTIAL:{label}]")

        is_clean = (len(issues) == 0)
        return is_clean, issues, sanitized


# =============================================================================
# 3. VERIFICADOR DE ALUCINACIONES Y COHERENCIA DE APIS (HALLUCINATION DETECTOR)
# =============================================================================
class HallucinationDetector:
    """Verifica la validez y consistencia técnica de APIs conocidas y el ecosistema JEV."""

    KNOWN_HALLUCINATIONS = [
        # Constructores inexistentes en Three.js
        (r"THREE\.ArrowGeometry", "Three.js no posee 'THREE.ArrowGeometry'. Debe usarse THREE.ArrowHelper o combinación Cilindro+Cono."),
        (r"THREE\.SkyboxGeometry", "Three.js no tiene 'THREE.SkyboxGeometry'. Usar THREE.BoxGeometry con caras invertidas."),
        (r"THREE\.MeshPhysicsMaterial", "Constructor inventado: Three.js no tiene 'THREE.MeshPhysicsMaterial' nativo."),
        # Inyección errónea de renderer en scripts del viewport
        (r"new\s+THREE\.WebGLRenderer", "Creación redundante de WebGLRenderer en Viewport. Se debe operar sobre window.renderer / window.scene existente."),
        # Paquetes inventados en Python
        (r"import\s+threejs\b", "Módulo de Python inexistente: 'threejs'. Three.js opera exclusivamente en el frontend JavaScript."),
        (r"import\s+react\b", "Módulo inexistente en runtime Python: 'react'."),
        # Antipatrón pip en módulos de la stdlib
        (r"pip\s+install\s+asyncio\b", "Alucinación de dependencias: 'asyncio' es parte de la biblioteca estándar de Python y nunca debe instalarse con pip."),
        (r"pip\s+install\s+socket\b", "Alucinación de dependencias: 'socket' es parte de la biblioteca estándar de Python."),
        (r"pip\s+install\s+threading\b", "Alucinación de dependencias: 'threading' es parte de la biblioteca estándar de Python."),
    ]

    @classmethod
    def check(cls, text: str) -> Tuple[bool, List[str], List[str]]:
        """
        Comprueba alucinaciones de API.
        Retorna (is_clean, issues, recommendations).
        """
        if not text:
            return True, [], []

        issues = []
        recommendations = []

        for pattern, explanation in cls.KNOWN_HALLUCINATIONS:
            match = re.search(pattern, text)
            if match:
                issues.append(f"Alucinación de API detectada: '{match.group(0)}' ({explanation})")
                recommendations.append(explanation)

        is_clean = (len(issues) == 0)
        return is_clean, issues, recommendations


# =============================================================================
# 4. AUDITOR ESTÁTICO DE CÓDIGO Y EDGE CASES (CODE ARTIFACT AUDITOR)
# =============================================================================
class CodeArtifactAuditor:
    """Audita la robustez estática de código generado antes de su entrega o persistencia."""

    @classmethod
    def audit_python_code(cls, code: str) -> Tuple[bool, int, List[str]]:
        """
        Inspecciona el código Python mediante AST en busca de riesgos:
        - Sintaxis errónea.
        - Bucles infinitos sin condición de ruptura (`while True:` sin break/return).
        - Bloques 'except: pass' ciegos.
        - División estática entre cero.
        Retorna (is_robust, score, issues).
        """
        if not code.strip():
            return True, 100, []

        issues = []
        score = 100

        # 1. Comprobación sintáctica
        try:
            tree = ast.parse(code)
        except SyntaxError as se:
            return False, 0, [f"Error sintáctico irrecuperable: {se}"]

        # 2. Análisis de nodos AST
        for node in ast.walk(tree):
            # Detección de while True sin escape
            if isinstance(node, ast.While):
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    has_escape = False
                    for sub in ast.walk(node):
                        if isinstance(sub, (ast.Break, ast.Return, ast.Raise)):
                            has_escape = True
                            break
                    if not has_escape:
                        issues.append(f"Riesgo de bucle infinito terminal: 'while True' sin break/return en línea {node.lineno}.")
                        score -= 40

            # Detección de except: pass ciego
            elif isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    issues.append(f"Antipatrón de captura de errores silenciosa ('except: pass') en línea {node.lineno}.")
                    score -= 15

            # Detección de división por cero constante
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                if isinstance(node.right, ast.Constant) and node.right.value == 0:
                    issues.append(f"División estática entre cero detectada en línea {node.lineno}.")
                    score -= 30

        score = max(score, 10)
        is_robust = (score >= 70) and (len(issues) == 0 or all("Antipatrón" in i for i in issues))
        return is_robust, score, issues


# =============================================================================
# 5. AGENTE AUDITOR CENTRAL DE CONTROL DE CALIDAD Y RED-TEAMING (AGENT QA AUDITOR)
# =============================================================================
class AgentQAAuditor:
    """
    Motor central de QA y Red-Teaming de JEV inspirado en Giskard.
    Supervisa la seguridad adversarial de entradas y salidas, audita código
    y compila métricas de fiabilidad continuas en data/memory/qa_reports.jsonl.
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or default_config.memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.reports_file = self.memory_dir / "qa_reports.jsonl"
        self._total_scans = 0
        self._total_vulnerabilities = 0
        self._total_hallucinations = 0
        self._blocked_actions_count = 0

    def audit_response(self, response_text: str, context: str = "") -> QAAuditResult:
        """
        Auditoría exhaustiva sobre una respuesta generada por el agente antes de enviarla al usuario:
        1. Escaneo de inyección de prompt residual.
        2. Detección de fuga de credenciales con sanitización automática.
        3. Detección de alucinaciones de API del ecosistema JEV.
        """
        self._total_scans += 1
        t_now = datetime.now().isoformat()
        all_issues = []
        all_recs = []

        # 1. Prompt Injection Scan
        clean_inj, risk_inj, issues_inj = PromptInjectionScanner.scan(response_text)
        all_issues.extend(issues_inj)

        # 2. Credential Leak Detection
        clean_cred, issues_cred, sanitized_txt = CredentialLeakDetector.scan_and_sanitize(response_text)
        all_issues.extend(issues_cred)

        # 3. Hallucination Detection
        clean_halluc, issues_halluc, recs_halluc = HallucinationDetector.check(response_text)
        all_issues.extend(issues_halluc)
        all_recs.extend(recs_halluc)

        vuln_count = len(issues_inj) + len(issues_cred) + len(issues_halluc)
        self._total_vulnerabilities += vuln_count
        if issues_halluc:
            self._total_hallucinations += len(issues_halluc)

        # Seguridad general
        is_safe = (len(issues_cred) == 0 and len(issues_inj) == 0)
        risk_score = min(vuln_count * 0.3, 1.0)

        if not is_safe:
            self._blocked_actions_count += 1

        result = QAAuditResult(
            timestamp=t_now,
            audit_type="full_response_scan",
            is_safe=is_safe,
            risk_score=risk_score,
            vulnerabilities_count=vuln_count,
            issues=all_issues,
            recommendations=all_recs,
            metrics={
                "has_credential_leaks": not clean_cred,
                "has_prompt_injection": not clean_inj,
                "has_hallucinations": not clean_halluc,
                "hallucination_rate": round(len(issues_halluc) / max(1, len(all_issues) + 1), 2)
            },
            sanitized_output=sanitized_txt if not clean_cred else response_text
        )

        self._persist_report(result)
        return result

    def audit_code_artifact(self, code_str: str, filename: str = "snippet.py", context: str = "") -> QAAuditResult:
        """
        Audita un script o artefacto de código antes de persistirlo en workspace/ o ejecutarlo.
        """
        self._total_scans += 1
        t_now = datetime.now().isoformat()
        is_robust, score, issues = CodeArtifactAuditor.audit_python_code(code_str)

        # También verificar que el código no contenga fuga de credenciales hardcodeadas
        clean_cred, issues_cred, sanitized_code = CredentialLeakDetector.scan_and_sanitize(code_str)
        all_issues = issues + issues_cred

        vuln_count = len(all_issues)
        self._total_vulnerabilities += vuln_count

        is_safe = is_robust and clean_cred
        risk_score = round(1.0 - (score / 100.0), 2)

        result = QAAuditResult(
            timestamp=t_now,
            audit_type="code_robustness",
            is_safe=is_safe,
            risk_score=risk_score,
            vulnerabilities_count=vuln_count,
            issues=all_issues,
            recommendations=[f"Revisar robustez de {filename}."] if not is_safe else ["Código validado para ejecución."],
            metrics={
                "robustness_score": score,
                "filename": filename,
                "has_hardcoded_secrets": not clean_cred
            },
            sanitized_output=sanitized_code
        )

        self._persist_report(result)
        return result

    def sanitize_or_correct(self, response_text: str, report: QAAuditResult) -> str:
        """
        Aplica sanitización inmediata sobre una respuesta con vulnerabilidades detectadas.
        Si hubo fuga de credenciales, sustituye por tokens protegidos.
        Si hubo inyección severa, bloquea la salida y devuelve un mensaje de neutralización.
        """
        # 1. Si hay sanitizado disponible por credenciales, usarlo
        out = report.sanitized_output or response_text

        # 2. Si hubo inyección de prompt severa que comprometa la integridad
        if any("inyección de prompt" in issue.lower() for issue in report.issues):
            out = (
                "🛡️ [INTERCEPTOR DE SEGURIDAD QA]: La respuesta generada contenía patrones adversariales "
                "o intentos de override de instrucciones de sistema y ha sido neutralizada."
            )

        return out

    def get_shield_status(self) -> Dict[str, Any]:
        """Devuelve el estado del Escudo de Seguridad QA para telemetría y UI."""
        status_label = (
            f"Escudo QA: Activo | Vulnerabilidades: {self._total_vulnerabilities}"
            if self._total_vulnerabilities == 0
            else f"Escudo QA: Alerta | Vulnerabilidades: {self._total_vulnerabilities}"
        )
        return {
            "shield_active": True,
            "status_label": status_label,
            "total_scans": self._total_scans,
            "total_vulnerabilities": self._total_vulnerabilities,
            "total_hallucinations": self._total_hallucinations,
            "blocked_actions": self._blocked_actions_count,
            "giskard_backend_available": GISKARD_AVAILABLE
        }

    def _persist_report(self, result: QAAuditResult) -> None:
        """Almacena el informe en data/memory/qa_reports.jsonl."""
        try:
            with open(self.reports_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_recent_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Recupera los últimos informes de auditoría."""
        if not self.reports_file.exists():
            return []
        try:
            with open(self.reports_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return [json.loads(line) for line in lines[-limit:]]
        except Exception:
            return []
