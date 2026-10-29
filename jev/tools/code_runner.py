"""
Herramientas de ejecución de código y comandos de sistema para JEV.
Permite ejecutar scripts de Python y comandos de consola (PowerShell/CMD) con control de timeouts.
"""
from typing import Dict, Any, Optional
import subprocess
import tempfile
import sys
import os
import re
import time
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config
from jev.core.sandbox import ExecutionSandbox


import psutil

MAX_EXECUTION_TIMEOUT = 120  # Techo máximo absoluto para evitar cuelgues indefinidos
MAX_OUTPUT_CHARS = 8000


def kill_process_tree(pid: int) -> None:
    """Termina de forma forzada un proceso y toda su descendencia para evitar procesos zombi."""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
            except Exception:
                pass


def safe_subprocess_run(cmd: Any, cwd: Any, env: Optional[Dict[str, str]] = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un subproceso con timeout estricto y terminación forzosa de la jerarquía de procesos."""
    effective_timeout = min(max(1, timeout), MAX_EXECUTION_TIMEOUT)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags
    )
    try:
        stdout, stderr = proc.communicate(timeout=effective_timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        try:
            proc.kill()
        except Exception:
            pass
        raise subprocess.TimeoutExpired(cmd, effective_timeout)


class PythonRunnerTool(BaseTool):
    """Ejecuta código Python en un subproceso aislado y captura la salida con timeouts estrictos."""
    name = "execute_python"
    description = (
        "Ejecuta código Python en un subproceso independiente y devuelve stdout, stderr y código de salida. "
        "Ideal para cálculos, procesamiento de datos, scripts y pruebas."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Código fuente Python a ejecutar."
            },
            "timeout": {
                "type": "integer",
                "description": "Tiempo máximo en segundos de ejecución (máximo permitido 120s)."
            }
        },
        "required": ["code"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, code: str, timeout: int = 30, **kwargs) -> ToolResult:
        try:
            # Validación estricta preventiva de código peligroso
            dangerous_patterns = [
                r":\(\)\s*\{.*?\}\s*;:",  # fork bomb
                r"shutil\.rmtree\s*\(\s*['\"][a-zA-Z]:[\\/]*['\"]\s*\)",
                r"shutil\.rmtree\s*\(\s*['\"][\\/]['\"]\s*\)",
                r"os\.system\s*\(\s*['\"]format\s+[a-zA-Z]:",
                r"format\s+[a-zA-Z]:",
            ]
            clean_code = code.replace("\\\\", "/").replace("\\", "/")
            for pat in dangerous_patterns:
                if re.search(pat, code, re.IGNORECASE) or re.search(pat, clean_code, re.IGNORECASE):
                    return ToolResult(
                        success=False,
                        output="",
                        error="Bloqueo de seguridad: El script contiene operaciones destructivas prohibidas."
                    )

            # Guardia anti-regresión del Viewport 3D: el canal correcto para
            # geometría es skill_cad_mesh / render_3d_scene, nunca Python con JS.
            js_markers = ("new THREE.", "THREE.BufferGeometry", "THREE.WebGLRenderer")
            if any(marker in code for marker in js_markers):
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Código JavaScript detectado dentro de execute_python. Python se ejecuta en el "
                        "backend y no puede renderizar en el Viewport 3D. Usa 'skill_cad_mesh' para piezas "
                        "paramétricas o 'render_3d_scene' para escenas declarativas; 'execute_viewport_script' "
                        "solo para animar la escena activa."
                    )
                )

            # Usar el intérprete actual (el del venv)
            python_bin = sys.executable

            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{str(self.workspace_dir)}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(self.workspace_dir)

            start_time = time.time()
            try:
                proc = safe_subprocess_run(
                    [python_bin, tmp_path],
                    cwd=str(self.workspace_dir),
                    env=env,
                    timeout=timeout
                )
                duration = time.time() - start_time
                stdout = proc.stdout.strip()
                stderr = proc.stderr.strip()
                exit_code = proc.returncode

                # Truncamiento de seguridad para evitar desbordamiento de contexto
                if len(stdout) > MAX_OUTPUT_CHARS:
                    stdout = stdout[:MAX_OUTPUT_CHARS] + "\n... [SALIDA TRUNCADA POR SEGURIDAD DE MEMORIA] ..."
                if len(stderr) > MAX_OUTPUT_CHARS:
                    stderr = stderr[:MAX_OUTPUT_CHARS] + "\n... [ERROR TRUNCADO POR SEGURIDAD DE MEMORIA] ..."

                output_parts = [f"Ejecución finalizada en {duration:.2f}s con código de salida {exit_code}."]
                if stdout:
                    output_parts.append(f"\n--- STDOUT ---\n{stdout}")
                if stderr:
                    output_parts.append(f"\n--- STDERR ---\n{stderr}")
                if not stdout and not stderr:
                    output_parts.append("\n(El script no generó salida por consola).")

                return ToolResult(
                    success=(exit_code == 0),
                    output="\n".join(output_parts),
                    error=stderr if exit_code != 0 else None,
                    data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr, "duration": duration}
                )
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Tiempo de ejecución excedido (timeout estricto de {min(timeout, MAX_EXECUTION_TIMEOUT)}s). Proceso cancelado."
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error ejecutando código Python: {str(e)}"
            )


class ShellCommandTool(BaseTool):
    """Ejecuta un comando de consola (PowerShell en Windows) con sandbox y timeouts estrictos."""
    name = "execute_command"
    description = (
        "Ejecuta un comando en la consola de comandos (PowerShell en Windows) "
        "dentro del directorio de trabajo y captura su salida."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Comando de consola a ejecutar (ej: 'dir', 'git status', 'pip list')."
            },
            "timeout": {
                "type": "integer",
                "description": "Tiempo límite en segundos (máximo permitido 120s, por defecto 45s)."
            }
        },
        "required": ["command"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, command: str, timeout: int = 45, **kwargs) -> ToolResult:
        try:
            # Validación mediante Sandbox de seguridad
            is_safe, error_msg = ExecutionSandbox.validate_command(command)
            if not is_safe:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Bloqueo de seguridad del Sandbox: {error_msg}"
                )

            import base64
            # Para evitar que PowerShell distorsione comillas, pipes, operadores de formato (-f) o flags (-AutoSize),
            # codificamos en Base64 UTF-16LE (-EncodedCommand). Para scripts muy extensos (>4000 chars), usamos un archivo temporal .ps1.
            start_time = time.time()
            tmp_ps_path = None
            try:
                if len(command) > 4000:
                    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as ps_tmp:
                        ps_tmp.write(command)
                        tmp_ps_path = ps_tmp.name
                    shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", tmp_ps_path]
                else:
                    encoded_cmd = base64.b64encode(command.encode("utf-16le")).decode("ascii")
                    shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_cmd]

                proc = safe_subprocess_run(
                    shell_cmd,
                    cwd=str(self.workspace_dir),
                    timeout=timeout
                )
            finally:
                if tmp_ps_path and os.path.exists(tmp_ps_path):
                    try:
                        os.unlink(tmp_ps_path)
                    except Exception:
                        pass
            duration = time.time() - start_time
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            if "#< CLIXML" in stderr and "progress" in stderr:
                stderr = re.sub(r"#<\s*CLIXML[\s\S]*?</Objs>", "", stderr).strip()
            exit_code = proc.returncode

            # Truncamiento de seguridad
            if len(stdout) > MAX_OUTPUT_CHARS:
                stdout = stdout[:MAX_OUTPUT_CHARS] + "\n... [SALIDA TRUNCADA POR SEGURIDAD DE MEMORIA] ..."
            if len(stderr) > MAX_OUTPUT_CHARS:
                stderr = stderr[:MAX_OUTPUT_CHARS] + "\n... [ERROR TRUNCADO POR SEGURIDAD DE MEMORIA] ..."

            output_parts = [f"Comando completado en {duration:.2f}s (código: {exit_code})."]
            if stdout:
                output_parts.append(f"\n--- SALIDA ---\n{stdout}")
            if stderr:
                output_parts.append(f"\n--- ERROR ---\n{stderr}")
            if not stdout and not stderr:
                output_parts.append("\n(Sin salida de consola).")

            return ToolResult(
                success=(exit_code == 0),
                output="\n".join(output_parts),
                error=stderr if exit_code != 0 else None,
                data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"El comando excedió el tiempo límite estricto de {min(timeout, MAX_EXECUTION_TIMEOUT)}s. Proceso cancelado."
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error ejecutando comando de shell: {str(e)}"
            )


class PackageManagerTool(BaseTool):
    """Instala paquetes y dependencias Python en el entorno virtual local."""
    name = "install_python_package"
    description = (
        "Instala o actualiza una librería de Python dentro del entorno virtual .venv "
        "usando pip (ej: 'numpy', 'scipy', 'sympy', 'pillow', 'fastapi'). "
        "Permite al agente dotarse de dependencias faltantes para ejecutar scripts."
    )
    parameters = {
        "type": "object",
        "properties": {
            "package_name": {
                "type": "string",
                "description": "Nombre del paquete o especificación (ej: 'pandas', 'matplotlib>=3.5')."
            }
        },
        "required": ["package_name"]
    }

    def execute(self, package_name: str, **kwargs) -> ToolResult:
        try:
            package_clean = package_name.strip()
            if any(ch in package_clean for ch in [";", "&", "|", "`", "$"]):
                return ToolResult(success=False, output="", error="Nombre de paquete no válido.")

            python_bin = sys.executable
            cmd = [python_bin, "-m", "pip", "install", package_clean]

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output=f"Paquete '{package_clean}' instalado exitosamente en el entorno virtual.\n{proc.stdout.strip()[:300]}",
                    data={"package": package_clean}
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fallo al instalar '{package_clean}': {proc.stderr.strip()[:400]}"
                )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Timeout durante la instalación de '{package_name}'.")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error instalando paquete: {str(e)}")
