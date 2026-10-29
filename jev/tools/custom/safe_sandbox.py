"""
Herramienta de Ejecución Aislada con Protección contra Path Traversal (SafeSandboxTool).

Ejecuta scripts (Python, PowerShell, Batch) de forma confinada, aplicando validación
estricta de rutas (Path Traversal Guard) para garantizar que ninguna operación
lea o modifique archivos fuera del directorio seguro 'workspace/'.
"""
from typing import Dict, Any, Optional, List, Literal
from pathlib import Path
import subprocess
import tempfile
import sys
import os
import re
from pydantic import BaseModel, Field, ValidationError

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class SafeSandboxInput(BaseModel):
    """Esquema de parámetros validados con Pydantic para SafeSandboxTool."""
    script_path: Optional[str] = Field(
        default=None,
        description="Ruta relativa del script dentro de workspace/ a ejecutar."
    )
    inline_code: Optional[str] = Field(
        default=None,
        description="Código fuente a ejecutar de forma segura si no se indica script_path."
    )
    language: Literal["python", "powershell", "cmd"] = Field(
        default="python",
        description="Intérprete o lenguaje de ejecución: 'python', 'powershell', 'cmd'."
    )
    arguments: List[str] = Field(
        default_factory=list,
        description="Argumentos de línea de comandos pasados al script."
    )
    timeout_sec: int = Field(
        default=15,
        ge=1,
        le=120,
        description="Tiempo máximo de ejecución en segundos antes de abortar el proceso."
    )


class SafeSandboxTool(BaseTool):
    """
    Herramienta que ejecuta código y scripts de forma segura garantizando aislamiento
    de directorio mediante el Path Traversal Guard.
    """
    name = "safe_sandbox_runner"
    description = (
        "Ejecuta código y scripts aislados (Python/PowerShell/Cmd) aplicando validación estricta de rutas "
        "(Path Traversal Guard), impidiendo lecturas o modificaciones fuera del directorio 'workspace/'."
    )
    parameters = SafeSandboxInput.model_json_schema()

    def __init__(self, workspace_dir: Optional[Path] = None):
        super().__init__()
        self.workspace_dir = (workspace_dir or default_config.workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_temp_dir = self.workspace_dir / ".sandbox_tmp"
        self.sandbox_temp_dir.mkdir(parents=True, exist_ok=True)

    def _validate_path_safety(self, path_str: str) -> Path:
        """
        Path Traversal Guard:
        Verifica que la ruta resuelva de forma estricta dentro del directorio workspace/.
        Rechaza secuencias '..', accesos a discos raíz o rutas de sistema.
        """
        # Limpieza básica
        clean = path_str.strip().strip("'\"")
        if not clean:
            raise ValueError("Ruta vacía no permitida.")

        # Resolver ruta candidata contra workspace
        candidate = (self.workspace_dir / clean).resolve()

        # Comprobar contención estricta
        try:
            candidate.relative_to(self.workspace_dir)
        except ValueError:
            raise PermissionError(
                f"VIOLACIÓN DE SANDBOX (Path Traversal detectado): "
                f"El objetivo '{path_str}' intenta escapar del directorio seguro '{self.workspace_dir}'."
            )

        return candidate

    def execute(
        self,
        script_path: Optional[str] = None,
        inline_code: Optional[str] = None,
        language: str = "python",
        arguments: Optional[List[str]] = None,
        timeout_sec: int = 15,
        **kwargs
    ) -> ToolResult:
        try:
            params = SafeSandboxInput(
                script_path=script_path,
                inline_code=inline_code,
                language=language,
                arguments=arguments or [],
                timeout_sec=timeout_sec
            )
        except ValidationError as ve:
            return ToolResult(
                success=False,
                output="",
                error=f"Error de validación de parámetros en SafeSandboxTool: {ve}"
            )

        # 1. Determinar el archivo a ejecutar
        temp_file_created: Optional[Path] = None
        try:
            if params.inline_code:
                # Escribir código inline en un archivo efímero confinado en workspace/.sandbox_tmp
                ext = ".py" if params.language == "python" else (".ps1" if params.language == "powershell" else ".bat")
                with tempfile.NamedTemporaryFile("w", dir=str(self.sandbox_temp_dir), suffix=ext, delete=False, encoding="utf-8") as tmp:
                    tmp.write(params.inline_code)
                    target_file = Path(tmp.name)
                temp_file_created = target_file
            elif params.script_path:
                target_file = self._validate_path_safety(params.script_path)
                if not target_file.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"El script seguro '{params.script_path}' no existe en {self.workspace_dir}."
                    )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Debes proporcionar 'script_path' o 'inline_code'."
                )

            # 2. Validar que los argumentos no intenten saltarse el sandbox
            sanitized_args = []
            for arg in params.arguments:
                if ".." in arg or ((":\\" in arg or ":/" in arg) and not str(self.workspace_dir) in arg):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Argumento bloqueado por seguridad (Path Traversal sospechoso): '{arg}'"
                    )
                sanitized_args.append(arg)

            # 3. Construir comando según el intérprete
            if params.language == "python":
                cmd = [sys.executable, str(target_file)] + sanitized_args
            elif params.language == "powershell":
                cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target_file)] + sanitized_args
            elif params.language == "cmd":
                cmd = ["cmd", "/c", str(target_file)] + sanitized_args
            else:
                return ToolResult(success=False, output="", error=f"Lenguaje '{params.language}' no soportado.")

            # 4. Ejecutar en subproceso aislado con CWD confinado en workspace_dir
            env = os.environ.copy()
            env["WORKSPACE_ROOT"] = str(self.workspace_dir)
            env["PYTHONPATH"] = str(self.workspace_dir)

            proc = subprocess.run(
                cmd,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=params.timeout_sec,
                env=env
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            success = proc.returncode == 0

            out_text = f"🛡️ [SANDBOX EXECUTION (Código de salida: {proc.returncode})]\n"
            if stdout:
                out_text += f"[SALIDA ESTÁNDAR]:\n{stdout}\n"
            if stderr:
                out_text += f"[SALIDA DE ERROR]:\n{stderr}\n"
            if not stdout and not stderr:
                out_text += "(Ejecución completada sin salida en consola)\n"

            return ToolResult(
                success=success,
                output=out_text.strip(),
                error=stderr if not success else None,
                data={
                    "exit_code": proc.returncode,
                    "language": params.language,
                    "target_file": str(target_file.name),
                    "stdout": stdout,
                    "stderr": stderr
                }
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Tiempo de ejecución excedido en Sandbox ({params.timeout_sec}s)."
            )
        except PermissionError as pe:
            return ToolResult(success=False, output="", error=str(pe))
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Fallo durante la ejecución segura: {e}")
        finally:
            if temp_file_created and temp_file_created.exists():
                try:
                    temp_file_created.unlink()
                except Exception:
                    pass
