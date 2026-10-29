"""
Motor de Ejecución (ExecutionEngine) para Muse Spark en JEV.
Gestiona la ejecución aislada y segura de herramientas, subprocesos del sistema
y funciones Python nativas, capturando stdout, stderr, códigos de salida y métricas.
"""
from typing import Dict, Any, Optional, Tuple
import subprocess
import asyncio
import base64
import time
import json
import sys
import os
import psutil
import logging
from dataclasses import dataclass, field
from pathlib import Path

from jev.core.muse.tool_registry import ToolRegistry, ToolDefinition
from jev.core.sandbox import ExecutionSandbox
from jev.config import default_config

logger = logging.getLogger("jev.muse.execution_engine")

MAX_OUTPUT_CHARS = 10000


@dataclass
class ExecutionResult:
    """Resultado estandarizado de una acción ejecutada."""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    data: Optional[Dict[str, Any]] = None
    duration: float = 0.0

    def to_context_str(self) -> str:
        """Formatea el resultado para ser inyectado como contexto en el siguiente turno."""
        parts = []
        status_tag = "ÉXITO" if self.success else f"FALLO (Código: {self.exit_code})"
        parts.append(f"[{status_tag}] (Duración: {self.duration:.2f}s)")
        if self.output:
            parts.append(f"--- STDOUT ---\n{self.output.strip()}")
        if self.error:
            parts.append(f"--- STDERR / ERROR ---\n{self.error.strip()}")
        if not self.output and not self.error:
            parts.append("(Sin salida producida)")
        return "\n".join(parts)


def kill_process_tree(pid: int) -> None:
    """Elimina forzosamente un subproceso y todos sus procesos hijos."""
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


class ExecutionEngine:
    """
    Arnés de ejecución desacoplado.
    Enruta llamadas a herramientas registradas, aplica sandboxing y gestiona timeouts.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        workspace_dir: Optional[Path] = None,
        default_timeout: int = 60
    ):
        self.registry = registry or ToolRegistry()
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.default_timeout = default_timeout

    def execute_action(self, action_name: str, params: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """
        Punto de entrada síncrono para ejecutar una acción estructurada.
        Soporta funciones nativas y subprocesos.
        """
        params = params or {}
        tool_def = self.registry.get_tool(action_name)

        if not tool_def:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Herramienta no encontrada: '{action_name}'. Herramientas disponibles: {self.registry.list_tools()}",
                exit_code=127
            )

        start_time = time.time()

        try:
            # Caso 1: Subproceso del Sistema Operativo
            if tool_def.is_shell_command:
                command = params.get("command", "")
                timeout = int(params.get("timeout", self.default_timeout))
                return self._execute_shell_subprocess(command, timeout=timeout)

            # Caso 2: Función Asíncrona
            if tool_def.is_async:
                # Correr en un event loop temporal o existente
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import nest_asyncio
                        nest_asyncio.apply()
                        res = loop.run_until_complete(tool_def.handler(**params))
                    else:
                        res = loop.run_until_complete(tool_def.handler(**params))
                except RuntimeError:
                    res = asyncio.run(tool_def.handler(**params))
                duration = time.time() - start_time
                return self._normalize_return_value(res, duration)

            # Caso 3: Función Python Síncrona o BaseTool
            res = tool_def.handler(**params)
            duration = time.time() - start_time
            return self._normalize_return_value(res, duration)

        except TypeError as te:
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=f"Error en los parámetros para '{action_name}': {str(te)}",
                exit_code=2,
                duration=duration
            )
        except Exception as exc:
            duration = time.time() - start_time
            logger.error(f"Excepción no controlada ejecutando '{action_name}': {exc}", exc_info=True)
            return ExecutionResult(
                success=False,
                output="",
                error=f"Excepción en '{action_name}': {str(exc)}",
                exit_code=1,
                duration=duration
            )

    def _execute_shell_subprocess(self, command: str, timeout: int = 60) -> ExecutionResult:
        """Ejecuta un comando en PowerShell/Bash con aislamiento sandbox y captura de salidas."""
        start_time = time.time()

        # 1. Validación de seguridad con ExecutionSandbox
        is_safe, error_msg = ExecutionSandbox.validate_command(command)
        if not is_safe:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Bloqueo de seguridad del Sandbox: {error_msg}",
                exit_code=126,
                duration=time.time() - start_time
            )

        # 2. Configuración de llamada a subproceso
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        if sys.platform == "win32":
            # Codificación Base64 UTF-16LE para evitar distorsiones de comillas y pipes
            encoded_cmd = base64.b64encode(command.encode("utf-16le")).decode("ascii")
            cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_cmd]
        else:
            cmd_args = ["/bin/bash", "-c", command]

        proc = None
        try:
            proc = subprocess.Popen(
                cmd_args,
                cwd=str(self.workspace_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            duration = time.time() - start_time
            exit_code = proc.returncode

            stdout_clean = stdout.strip()
            stderr_clean = stderr.strip()

            # Truncamiento de seguridad
            if len(stdout_clean) > MAX_OUTPUT_CHARS:
                stdout_clean = stdout_clean[:MAX_OUTPUT_CHARS] + "\n... [SALIDA TRUNCADA]"
            if len(stderr_clean) > MAX_OUTPUT_CHARS:
                stderr_clean = stderr_clean[:MAX_OUTPUT_CHARS] + "\n... [ERROR TRUNCADO]"

            return ExecutionResult(
                success=(exit_code == 0),
                output=stdout_clean,
                error=stderr_clean if exit_code != 0 else (stderr_clean or None),
                exit_code=exit_code,
                duration=duration
            )

        except subprocess.TimeoutExpired:
            if proc:
                kill_process_tree(proc.pid)
                try:
                    proc.kill()
                except Exception:
                    pass
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=f"Tiempo de ejecución excedido (Timeout estricto de {timeout}s). Proceso cancelado forzosamente.",
                exit_code=124,
                duration=duration
            )

    def _normalize_return_value(self, raw_result: Any, duration: float) -> ExecutionResult:
        """Normaliza el retorno de funciones Python o instancias ToolResult."""
        # Si devuelve un ToolResult de JEV
        if hasattr(raw_result, "success") and hasattr(raw_result, "output"):
            return ExecutionResult(
                success=bool(raw_result.success),
                output=str(raw_result.output or ""),
                error=str(raw_result.error) if raw_result.error else None,
                exit_code=0 if raw_result.success else 1,
                data=getattr(raw_result, "data", None),
                duration=duration
            )

        # Si devuelve un ExecutionResult
        if isinstance(raw_result, ExecutionResult):
            raw_result.duration = duration
            return raw_result

        # Si devuelve un booleano o tupla
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            success, output = raw_result
            return ExecutionResult(
                success=bool(success),
                output=str(output),
                exit_code=0 if success else 1,
                duration=duration
            )

        # Si devuelve un string o dict
        return ExecutionResult(
            success=True,
            output=str(raw_result) if not isinstance(raw_result, (dict, list)) else json.dumps(raw_result, indent=2),
            exit_code=0,
            duration=duration,
            data=raw_result if isinstance(raw_result, dict) else None
        )
