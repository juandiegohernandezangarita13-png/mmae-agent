"""
Herramienta de Elevación y Ejecución de Comandos con Privilegios Administrativos para JEV.
Permite ejecutar scripts o comandos que requieren permisos de Administrador en Windows
gestionando la captura de salida y códigos de salida sin bloquear el bucle del agente.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class SystemElevationTool(BaseTool):
    """Ejecuta comandos del sistema con permisos de Administrador en Windows."""
    name = "run_elevated_command"
    description = (
        "Ejecuta un comando o script en Windows con privilegios elevados de Administrador (RunAs). "
        "Úsalo para instalar controladores, configurar servicios de Windows, modificar variables de entorno "
        "del sistema o ejecutar tareas que requieran permisos elevados."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Comando de PowerShell o script a ejecutar con privilegios de Administrador."
            },
            "timeout": {
                "type": "number",
                "description": "Tiempo máximo en segundos de espera para la finalización (defecto 30s).",
                "default": 30.0
            }
        },
        "required": ["command"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, command: str, timeout: float = 30.0, **kwargs) -> ToolResult:
        cmd_clean = (command or "").strip()
        if not cmd_clean:
            return ToolResult(success=False, output="", error="El comando elevado no puede estar vacío.")

        if sys.platform != "win32":
            return ToolResult(success=False, output="", error="run_elevated_command solo está disponible en Windows.")

        # Verificar si el proceso actual ya corre como Administrador
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False

        temp_dir = Path(tempfile.gettempdir()) / "jev_elevated"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        out_file = temp_dir / f"out_{timestamp}.txt"
        err_file = temp_dir / f"err_{timestamp}.txt"
        code_file = temp_dir / f"code_{timestamp}.txt"

        # Si ya somos admin, ejecutar directamente en subproceso
        if is_admin:
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd_clean],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace"
                )
                msg = f"✓ Comando ejecutado con privilegios de Administrador (código: {proc.returncode}):\n{proc.stdout}"
                if proc.stderr:
                    msg += f"\n[stderr]: {proc.stderr}"
                return ToolResult(
                    success=(proc.returncode == 0),
                    output=msg,
                    data={"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error en comando elevado: {e}")

        # Si no somos admin, invocar mediante Start-Process powershell -Verb RunAs
        ps_wrapper = f"""
$ErrorActionPreference = 'Continue'
try {{
    & {{ {cmd_clean} }} 1> "{out_file}" 2> "{err_file}"
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {{ $exitCode = 0 }}
}} catch {{
    $_ | Out-File -FilePath "{err_file}" -Append
    $exitCode = 1
}}
$exitCode | Out-File -FilePath "{code_file}" -Encoding ascii
"""
        script_file = temp_dir / f"script_{timestamp}.ps1"
        script_file.write_text(ps_wrapper, encoding="utf-8")

        launcher_ps = f"""
Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `\"{script_file}`\"" -Wait -WindowStyle Hidden
"""
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher_ps],
                timeout=timeout,
                capture_output=True
            )

            # Esperar a que los archivos de salida estén escritos
            time.sleep(0.5)

            out_text = out_file.read_text(encoding="utf-8", errors="replace") if out_file.exists() else ""
            err_text = err_file.read_text(encoding="utf-8", errors="replace") if err_file.exists() else ""
            code_str = code_file.read_text(encoding="ascii", errors="ignore").strip() if code_file.exists() else "0"
            exit_code = int(code_str) if code_str.isdigit() else 0

            # Limpiar temporales
            for f in (script_file, out_file, err_file, code_file):
                try:
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass

            status_str = "éxito" if exit_code == 0 else f"fallo (código {exit_code})"
            res_msg = f"✓ Proceso elevado completado con {status_str}.\nSalida:\n{out_text}"
            if err_text:
                res_msg += f"\nErrores:\n{err_text}"

            return ToolResult(
                success=(exit_code == 0),
                output=res_msg,
                data={"exit_code": exit_code, "stdout": out_text, "stderr": err_text}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"El comando elevado superó el timeout de {timeout}s.")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error invocando elevación RunAs: {e}")
