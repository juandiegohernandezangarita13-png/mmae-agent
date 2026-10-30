"""
Herramienta de Auto-Reparación y Curación de Código (AutoRepairCodeTool) para JEV.
"""
from typing import Dict, Any, Optional
from jev.tools.base import BaseTool, ToolResult
from jev.core.code_repairer import CodeAutoRepairer, default_code_repairer


class AutoRepairCodeTool(BaseTool):
    """Herramienta para auto-reparar código dañado o con bugs."""
    name = "repair_bad_code"
    description = (
        "Analiza, diagnostica y repara automáticamente código de Python con errores "
        "de sintaxis, importaciones faltantes, excepciones en runtime o lógica rota, "
        "validando su ejecución en sandbox."
    )
    parameters = {
        "type": "object",
        "properties": {
            "bad_code": {
                "type": "string",
                "description": "Código fuente en Python defectuoso o con errores a reparar."
            },
            "expected_output": {
                "type": "string",
                "description": "Texto o valor esperado que el código reparado debe generar al ejecutarse."
            }
        },
        "required": ["bad_code"]
    }

    def __init__(self, repairer: Optional[CodeAutoRepairer] = None):
        self.repairer = repairer or default_code_repairer

    def execute(self, bad_code: str, expected_output: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            res = self.repairer.repair_and_verify(bad_code=bad_code, expected_output=expected_output)
            if res.success:
                return ToolResult(
                    success=True,
                    output=(
                        f"✓ Código reparado exitosamente en {res.iterations} iteración(es) ({res.latency_ms:.1f}ms):\n"
                        f"--- CÓDIGO REPARADO ---\n{res.repaired_code}\n\n"
                        f"--- SALIDA DE EJECUCIÓN ---\n{res.execution_output}"
                    ),
                    data=res.to_dict()
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fallo al reparar código: {res.execution_error}",
                    data=res.to_dict()
                )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en reparación de código: {str(e)}")


__all__ = ["AutoRepairCodeTool"]
