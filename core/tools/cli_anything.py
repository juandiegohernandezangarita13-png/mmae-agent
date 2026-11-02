"""
Capa de Control y Ejecución Estandarizada del Sistema Operativo: CLI Anything.
Proporciona un wrapper robusto, tipado y seguro para ejecutar utilidades del sistema
operativo (PowerShell, CMD, Git, Python, Winget, FFmpeg, etc.) mediante interfaces
CLI estructuradas, con aislamiento de procesos, timeouts estrictos y salida normalizada en JSON.
"""
import subprocess
import shlex
import time
import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CLIExecutionResult:
    """Resultado estructurado de la ejecución de un comando CLI."""
    command: str
    executable: str
    arguments: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool
    success: bool
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        return res

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class CLICommandValidator:
    """Validador y saneador de argumentos para prevenir inyecciones de comandos en el SO."""

    DANGEROUS_SHELL_PATTERNS = [
        "&&", "||", ";", "`", "$(", "${",
        "format c:", "del /f /s /q c:\\windows", "rmdir /s /q c:\\windows",
        "drop database", "drop table"
    ]

    @classmethod
    def sanitize_arguments(cls, args: List[str]) -> List[str]:
        """Sanea la lista de argumentos asegurando tipos string y evitando inyecciones."""
        sanitized = []
        for arg in args:
            s_arg = str(arg).strip()
            # Verificar patrones de alto riesgo
            lower_arg = s_arg.lower()
            for pattern in cls.DANGEROUS_SHELL_PATTERNS:
                if pattern in lower_arg:
                    raise ValueError(f"Argumento rechazado por seguridad (patrón peligroso detectado: '{pattern}')")
            sanitized.append(s_arg)
        return sanitized


class CLIAnythingRunner:
    """
    Ejecutor central de herramientas CLI con aislamiento de subprocesos y control de timeout.
    """

    def __init__(self, default_timeout_seconds: float = 30.0, working_dir: Optional[Union[str, Path]] = None):
        self.default_timeout_seconds = default_timeout_seconds
        self.working_dir = Path(working_dir or os.getcwd()).resolve()

    def _kill_process_tree(self, pid: int) -> None:
        """Mata el árbol de procesos en Windows de forma implacable si expira el timeout."""
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )
            else:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception as e:
            logger.debug("Error terminando árbol de procesos %d: %s", pid, e)

    def execute(
        self,
        executable: str,
        arguments: Optional[List[str]] = None,
        working_dir: Optional[Union[str, Path]] = None,
        timeout_seconds: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None
    ) -> CLIExecutionResult:
        """
        Ejecuta un ejecutable del sistema con aislamiento y timeout estricto.
        """
        args = arguments or []
        try:
            sanitized_args = CLICommandValidator.sanitize_arguments(args)
        except ValueError as e:
            return CLIExecutionResult(
                command=f"{executable} {' '.join(args)}",
                executable=executable,
                arguments=args,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=0.0,
                timed_out=False,
                success=False
            )

        cwd = Path(working_dir or self.working_dir).resolve()
        timeout = timeout_seconds or self.default_timeout_seconds

        # Si el ejecutable es 'python', resolver al ejecutable activo del venv/entorno
        if executable.lower() in ("python", "python3"):
            resolved_exec = sys.executable
        else:
            resolved_exec = executable

        cmd_list = [resolved_exec] + sanitized_args
        cmd_str = f"{resolved_exec} {' '.join(sanitized_args)}"

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        start_time = time.perf_counter()
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        exit_code = -1

        try:
            proc = subprocess.Popen(
                cmd_list,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE if input_data else subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                shell=False
            )

            try:
                stdout_text, stderr_text = proc.communicate(
                    input=input_data,
                    timeout=timeout
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill_process_tree(proc.pid)
                stdout_text, stderr_text = proc.communicate()
                stderr_text = f"TIMEOUT: El comando excedió el límite de {timeout:.1f}s y fue terminado.\n" + (stderr_text or "")
                exit_code = -1

        except FileNotFoundError:
            stderr_text = f"Ejecutable no encontrado en el sistema: '{executable}'"
            exit_code = 127
        except Exception as e:
            stderr_text = f"Error del sistema al ejecutar subproceso: {str(e)}"
            exit_code = -1

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        success = (exit_code == 0) and not timed_out

        return CLIExecutionResult(
            command=cmd_str,
            executable=executable,
            arguments=sanitized_args,
            exit_code=exit_code,
            stdout=stdout_text.strip(),
            stderr=stderr_text.strip(),
            duration_ms=round(duration_ms, 2),
            timed_out=timed_out,
            success=success
        )

    def execute_powershell(
        self,
        command: str,
        timeout_seconds: Optional[float] = None,
        working_dir: Optional[Union[str, Path]] = None
    ) -> CLIExecutionResult:
        """
        Ejecuta un script o comando de PowerShell a través del wrapper seguro.
        """
        # Usar -NoProfile -NonInteractive -ExecutionPolicy Bypass para máxima estabilidad
        ps_args = [
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", command
        ]
        return self.execute(
            executable="powershell.exe",
            arguments=ps_args,
            working_dir=working_dir,
            timeout_seconds=timeout_seconds
        )


class CLIToolRegistry:
    """Registro de utilidades de línea de comandos predefinidas (CLI Anything Adapters)."""

    @staticmethod
    def git(runner: CLIAnythingRunner, subcommand: str, flags: Optional[List[str]] = None, cwd: Optional[str] = None) -> CLIExecutionResult:
        args = [subcommand] + (flags or [])
        return runner.execute("git", args, working_dir=cwd)

    @staticmethod
    def python_script(runner: CLIAnythingRunner, script_path: str, script_args: Optional[List[str]] = None, cwd: Optional[str] = None) -> CLIExecutionResult:
        args = [script_path] + (script_args or [])
        return runner.execute(sys.executable, args, working_dir=cwd)

    @staticmethod
    def pip_install(runner: CLIAnythingRunner, package_name: str, cwd: Optional[str] = None) -> CLIExecutionResult:
        args = ["-m", "pip", "install", package_name]
        return runner.execute(sys.executable, args, working_dir=cwd)

    @staticmethod
    def system_status(runner: CLIAnythingRunner) -> CLIExecutionResult:
        return runner.execute_powershell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Id, ProcessName, CPU, WorkingSet")
