"""
Herramienta de Auditoría de Seguridad y Control de Calidad LLM (Giskard QA & Red-Teaming Tool) para JEV.
Permite al agente y al DAG autoevaluar la seguridad adversarial,
prevenir fugas de credenciales y certificar la robustez del código.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.self_improvement.qa_auditor import AgentQAAuditor
from jev.config import default_config


class QAAuditorTool(BaseTool):
    """Herramienta de auditoría QA, red-teaming y validación estática de seguridad."""
    name = "skill_qa_auditor"
    description = (
        "Subsistema de Auditoría de Seguridad y Control de Calidad LLM (Giskard QA & Red-Teaming). "
        "Permite escanear inyecciones de prompts, detectar fuga de credenciales o API keys, "
        "verificar alucinaciones técnicas (ej. APIs inexistentes de Three.js) y certificar la robustez "
        "de scripts de código antes de su persistencia en el sistema."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción: 'audit_response', 'audit_code', 'scan_prompt_injection', 'get_qa_status'",
                "enum": ["audit_response", "audit_code", "scan_prompt_injection", "get_qa_status"],
                "default": "audit_response"
            },
            "text": {
                "type": "string",
                "description": "Texto o respuesta de modelo a auditar",
                "default": ""
            },
            "code": {
                "type": "string",
                "description": "Código fuente a evaluar estáticamente",
                "default": ""
            },
            "filename": {
                "type": "string",
                "description": "Nombre de archivo asociado al código",
                "default": "snippet.py"
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.auditor = AgentQAAuditor()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "audit_response")
        text = kwargs.get("text", "")
        code = kwargs.get("code", "")
        filename = kwargs.get("filename", "snippet.py")

        try:
            if action == "audit_response":
                if not text:
                    return ToolResult(success=False, output="", error="Parámetro 'text' requerido para 'audit_response'.")
                report = self.auditor.audit_response(text)
                return ToolResult(
                    success=True,
                    output=(
                        f"Auditoría QA finalizada: {'APROBADA (Seguro)' if report.is_safe else 'ALERTA (Inseguro)'}. "
                        f"Vulnerabilidades={report.vulnerabilities_count}, Riesgo={report.risk_score}."
                    ),
                    data=report.to_dict()
                )

            elif action == "audit_code":
                if not code:
                    return ToolResult(success=False, output="", error="Parámetro 'code' requerido para 'audit_code'.")
                report = self.auditor.audit_code_artifact(code, filename=filename)
                return ToolResult(
                    success=True,
                    output=(
                        f"Auditoría de código finalizada: {'ROBUSTO' if report.is_safe else 'OBSERVACIONES'}. "
                        f"Score={report.metrics.get('robustness_score', 0)}/100, Problemas={len(report.issues)}."
                    ),
                    data=report.to_dict()
                )

            elif action == "scan_prompt_injection":
                from jev.self_improvement.qa_auditor import PromptInjectionScanner
                is_clean, risk, issues = PromptInjectionScanner.scan(text)
                return ToolResult(
                    success=True,
                    output=f"Escaneo de inyección de prompts: {'LIMPIO' if is_clean else 'INYECCIÓN DETECTADA'}. Riesgo={risk}.",
                    data={"is_clean": is_clean, "risk_score": risk, "issues": issues}
                )

            elif action == "get_qa_status":
                status = self.auditor.get_shield_status()
                return ToolResult(
                    success=True,
                    output=f"Estado del Escudo QA: {status['status_label']}. Escaneos totales={status['total_scans']}.",
                    data=status
                )

            else:
                return ToolResult(success=False, output="", error=f"Acción desconocida '{action}'.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en QAAuditorTool: {e}")
