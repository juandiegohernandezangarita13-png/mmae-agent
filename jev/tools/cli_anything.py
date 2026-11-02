"""
Herramienta de Agente: CLI Anything Operator (jev.tools.cli_anything).
Permite al agente ejecutar comandos y herramientas del sistema operativo mediante una
interfaz estructurada, tipada, aislada y con salida JSON estandarizada.
"""
from typing import Dict, Any, Optional, List
import json
import shlex

from jev.tools.base import BaseTool, ToolResult
from core.tools.cli_anything import CLIAnythingRunner, CLIExecutionResult


class CLIAnythingTool(BaseTool):
    """Herramienta de ejecución CLI estructurada y segura (CLI Anything Layer)."""
    name = "cli_execute_structured"
    description = (
        "Ejecuta herramientas y comandos del sistema operativo (PowerShell, Git, Python, Winget, etc.) "
        "a través del wrapper estandarizado 'CLI Anything'. Proporciona aislamiento de subprocesos, "
        "control estricto de timeout, prevención de inyecciones y reporte JSON estructurado con exit_code, "
        "duración en ms, stdout y stderr."
    )
    parameters = {
        "type": "object",
        "properties": {
            "executable": {
                "type": "string",
                "description": "Binario o ejecutable del sistema a invocar (ej: 'powershell', 'git', 'python', 'winget', 'where')."
            },
            "arguments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de argumentos o banderas estructuradas (ej: ['status'], ['--version'], ['-NoProfile', '-Command', 'dir'])."
            },
            "command": {
                "type": "string",
                "description": "Comando en cadena de texto simple (opcional, alternativa a executable+arguments). Se ejecutará mediante PowerShell seguro."
            },
            "working_dir": {
                "type": "string",
                "description": "Directorio de trabajo para la ejecución (opcional, por defecto el workspace activo)."
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Tiempo límite de ejecución en segundos antes de terminar el proceso (por defecto: 30.0s)."
            }
        }
    }

    def __init__(self, runner: Optional[CLIAnythingRunner] = None):
        self.runner = runner or CLIAnythingRunner()

    def execute(
        self,
        executable: Optional[str] = None,
        arguments: Optional[List[str]] = None,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs
    ) -> ToolResult:
        try:
            timeout = float(timeout_seconds) if timeout_seconds else 30.0

            # 1. Si se proporciona 'command', ejecutar vía powershell seguro
            if command and not executable:
                res: CLIExecutionResult = self.runner.execute_powershell(
                    command=command,
                    timeout_seconds=timeout,
                    working_dir=working_dir
                )
            # 2. Si se proporciona ejecutable y argumentos estructurados
            elif executable:
                args = arguments or []
                res = self.runner.execute(
                    executable=executable,
                    arguments=args,
                    working_dir=working_dir,
                    timeout_seconds=timeout
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Se debe especificar al menos 'executable' o 'command'."
                )

            # Construir salida amigable y estructurada
            summary_output = (
                f"[{res.executable}] Código: {res.exit_code} | Duración: {res.duration_ms:.1f}ms | Éxito: {res.success}\n"
            )
            if res.stdout:
                summary_output += f"--- STDOUT ---\n{res.stdout}\n"
            if res.stderr:
                summary_output += f"--- STDERR ---\n{res.stderr}\n"
            if not res.stdout and not res.stderr:
                summary_output += "(Comando completado sin salida por consola)\n"

            return ToolResult(
                success=res.success,
                output=summary_output.strip(),
                error=res.stderr if not res.success else None,
                data=res.to_dict()
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en CLIAnythingTool: {str(e)}"
            )
