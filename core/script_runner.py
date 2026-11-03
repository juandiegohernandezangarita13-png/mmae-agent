"""
Módulo Script Runner (Paradigma CodeAct / Factory Droid).
Permite la ejecución programática de scripts de Python locales en lote para
lecturas, filtros, inspecciones de archivos y validaciones del entorno.
Devuelve únicamente un JSON resumido y sanitizado al contexto del LLM para evitar
el desbordamiento de tokens y los volcados masivos en el historial.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BASE_DIR, WORKSPACE_DIR
from core.chronos import ExecutionTimer
from core.evaluator import OutputEvaluator
from utils.logger import log


@dataclass
class ScriptResult:
    """Resultado compacto y serializable de la ejecución de un script local."""
    success: bool
    exit_code: int
    duration_seconds: float
    summary_json: Dict[str, Any] = field(default_factory=dict)
    raw_stdout: str = ""
    raw_stderr: str = ""
    error: Optional[str] = None
    executed_script_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "duration_seconds": round(self.duration_seconds, 4),
            "summary_json": self.summary_json,
            "raw_stdout_sample": self.raw_stdout[:1000] if len(self.raw_stdout) > 1000 else self.raw_stdout,
            "raw_stderr": self.raw_stderr,
            "error": self.error,
        }


class ScriptRunner:
    """
    Ejecutor de scripts programáticos locales (CodeAct / Programmatic Tool Calling).
    Garantiza aislamiento temporal, validación de sintaxis previa y destilación a JSON compacto.
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        default_timeout_seconds: int = 30,
        python_executable: Optional[str] = None,
    ) -> None:
        self.working_dir = Path(working_dir or WORKSPACE_DIR)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout_seconds = default_timeout_seconds
        self.python_executable = python_executable or sys.executable

        # Directorio seguro para scripts efímeros
        self.temp_scripts_dir = self.working_dir / ".scripts_cache"
        self.temp_scripts_dir.mkdir(parents=True, exist_ok=True)

    def extract_python_code(self, raw_content: str) -> str:
        """Extrae el bloque de código Python si está contenido en bloques Markdown."""
        code_block = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", raw_content, re.IGNORECASE)
        if code_block:
            return code_block.group(1).strip()
        return raw_content.strip()

    def run_script(
        self,
        script_code: str,
        timeout_seconds: Optional[int] = None,
        extra_env: Optional[Dict[str, str]] = None,
        custom_cwd: Optional[Path] = None,
    ) -> ScriptResult:
        """
        Ejecuta el script de Python de forma local y controlada.
        Extrae y valida sintaxis, corre el proceso con timeout y devuelve un JSON resumido.
        """
        clean_code = self.extract_python_code(script_code)
        timeout = timeout_seconds or self.default_timeout_seconds
        cwd = custom_cwd or self.working_dir

        # 1. Validación estricta de sintaxis previa (OutputEvaluator)
        syntax_eval = OutputEvaluator.validate_python_code(clean_code)
        if not syntax_eval.get("valid", False):
            err_msg = syntax_eval.get("error", "Error de sintaxis en el código emitido.")
            log.warning(f"❌ [ScriptRunner]: Sintaxis rechazada: {err_msg}")
            return ScriptResult(
                success=False,
                exit_code=1,
                duration_seconds=0.0,
                summary_json={"status": "syntax_error", "details": err_msg},
                raw_stderr=err_msg,
                error=err_msg,
            )

        # 2. Guardar en archivo temporal controlado
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir=str(self.temp_scripts_dir),
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(clean_code)

        # 3. Configurar entorno
        env = os.environ.copy()
        # Asegurar PYTHONPATH para incluir el proyecto raíz
        project_root = str(BASE_DIR)
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{project_root};{current_pythonpath}" if current_pythonpath else project_root
        if extra_env:
            env.update(extra_env)

        stdout_text = ""
        stderr_text = ""
        exit_code = -1
        err_message: Optional[str] = None

        # 4. Ejecución instrumentada con ExecutionTimer
        with ExecutionTimer(name="script_runner_execution") as timer:
            try:
                proc = subprocess.run(
                    [self.python_executable, str(temp_path)],
                    cwd=str(cwd),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
                exit_code = proc.returncode
                stdout_text = proc.stdout
                stderr_text = proc.stderr
            except subprocess.TimeoutExpired:
                exit_code = 124
                err_message = f"Timeout excedido ({timeout}s) durante la ejecución del script."
                stderr_text = err_message
            except Exception as e:
                exit_code = 1
                err_message = f"Excepción en subproceso: {str(e)}"
                stderr_text = err_message
            finally:
                # Limpiar script temporal
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception:
                    pass

        # 5. Destilación a JSON resumido (Ahorro radical de tokens)
        summary_json = self._distill_output_to_json(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            duration=timer.duration_seconds,
        )

        success = (exit_code == 0)
        log.info(
            f"⚡ [ScriptRunner]: Salida exit_code={exit_code} | "
            f"Duración={timer.duration_seconds:.3f}s | Éxito={success}"
        )

        return ScriptResult(
            success=success,
            exit_code=exit_code,
            duration_seconds=timer.duration_seconds,
            summary_json=summary_json,
            raw_stdout=stdout_text,
            raw_stderr=stderr_text,
            error=err_message or (stderr_text.strip() if exit_code != 0 else None),
            executed_script_path=str(temp_path),
        )

    def _distill_output_to_json(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
    ) -> Dict[str, Any]:
        """
        Extrae o construye un JSON conciso para el LLM, eliminando ruidos y volcados innecesarios.
        """
        # Intentar extraer bloques JSON explícitos generados por el script
        clean_stdout = stdout.strip()

        # Caso A: El script imprimió directamente un JSON
        if clean_stdout.startswith("{") and clean_stdout.endswith("}"):
            try:
                parsed = json.loads(clean_stdout)
                if isinstance(parsed, dict):
                    parsed["_execution_meta"] = {"exit_code": exit_code, "duration_seconds": round(duration, 3)}
                    return parsed
            except json.JSONDecodeError:
                pass

        # Caso B: Bloque delimitado <json_result>...</json_result>
        tag_match = re.search(r"<json_result>\s*([\s\S]*?)\s*</json_result>", clean_stdout)
        if tag_match:
            try:
                parsed = json.loads(tag_match.group(1))
                if isinstance(parsed, dict):
                    parsed["_execution_meta"] = {"exit_code": exit_code, "duration_seconds": round(duration, 3)}
                    return parsed
            except json.JSONDecodeError:
                pass

        # Caso C: Buscar el último bloque de llaves { ... }
        brace_matches = list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", clean_stdout))
        if brace_matches:
            last_match = brace_matches[-1].group(0)
            try:
                parsed = json.loads(last_match)
                if isinstance(parsed, dict):
                    parsed["_execution_meta"] = {"exit_code": exit_code, "duration_seconds": round(duration, 3)}
                    return parsed
            except json.JSONDecodeError:
                pass

        # Caso D: Fallback sintético compacto
        lines = [line.strip() for line in clean_stdout.splitlines() if line.strip()]
        return {
            "status": "success" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "duration_seconds": round(duration, 3),
            "lines_count": len(lines),
            "output_summary": lines[-5:] if len(lines) > 5 else lines,
            "error_summary": stderr.strip().splitlines()[-3:] if stderr.strip() else [],
        }


__all__ = ["ScriptRunner", "ScriptResult"]
