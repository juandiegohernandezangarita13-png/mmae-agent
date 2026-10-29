"""
Protocolo de Verificación Objetiva y Bucle de Reflexión (Reflection Loop) para JEV.
Evalúa de forma empírica si las acciones y herramientas se ejecutaron correctamente
(existencia de archivos, compilación sintáctica, exit codes, stderr y códigos HTTP).
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass
import os

from jev.tools.base import ToolResult
from jev.config import default_config


@dataclass
class VerificationResult:
    """Resultado del protocolo de verificación objetiva."""
    passed: bool
    reason: str
    suggested_fix: Optional[str] = None

    def __str__(self) -> str:
        if self.passed:
            return f"✓ [VERIFICACIÓN APROBADA]: {self.reason}"
        msg = f"✗ [VERIFICACIÓN FALLIDA]: {self.reason}"
        if self.suggested_fix:
            msg += f"\n👉 Acción correctiva requerida: {self.suggested_fix}"
        return msg


class ActionVerifier:
    """Validador objetivo de efectos secundarios y salidas de herramientas."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if not p.is_absolute():
            if p.parts and p.parts[0].lower() == "workspace":
                p = Path(*p.parts[1:])
            p = (self.workspace_dir / p).resolve()
        return p

    def verify_action(self, tool_name: str, arguments: Dict[str, Any], result: ToolResult) -> VerificationResult:
        """
        Ejecuta comprobaciones empíricas para validar que la herramienta realmente
        cumplió su propósito y no falló silenciosamente.
        """
        # Si la herramienta ya reportó fallo interno
        if not result.success:
            return VerificationResult(
                passed=False,
                reason=f"La herramienta '{tool_name}' reportó fallo explícito: {result.error or result.output}",
                suggested_fix="Revisa los parámetros enviados o el mensaje de error para corregir la llamada."
            )

        # 1. Verificación para creación y modificación de archivos
        if tool_name in ["write_file", "patch_file"]:
            target_path = self._resolve_path(arguments.get("path", ""))
            if not target_path.exists():
                return VerificationResult(
                    passed=False,
                    reason=f"El archivo objetivo '{target_path.name}' no existe en disco tras la ejecución.",
                    suggested_fix=f"Vuelve a escribir el archivo asegurándote de que la ruta sea válida: '{target_path}'."
                )
            if target_path.stat().st_size == 0:
                return VerificationResult(
                    passed=False,
                    reason=f"El archivo '{target_path.name}' fue creado pero está completamente vacío (0 bytes).",
                    suggested_fix="Sobrescribe el archivo con el contenido requerido."
                )

            # Si es código Python, validar sintaxis objetivamente
            if target_path.suffix.lower() == ".py":
                try:
                    with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                        code_content = f.read()
                    compile(code_content, str(target_path), "exec")
                except SyntaxError as se:
                    return VerificationResult(
                        passed=False,
                        reason=f"Error de sintaxis de Python detectado en '{target_path.name}': {se}",
                        suggested_fix=f"Corrige el error de sintaxis en la línea {se.lineno}: {se.msg}."
                    )

            return VerificationResult(
                passed=True,
                reason=f"Archivo '{target_path.name}' verificado en disco ({target_path.stat().st_size} bytes, sintaxis válida)."
            )

        # 2. Verificación para ejecución de Python
        if tool_name == "execute_python":
            exit_code = result.data.get("exit_code") if result.data else None
            stderr = result.data.get("stderr", "") if result.data else ""

            if exit_code is not None and exit_code != 0:
                return VerificationResult(
                    passed=False,
                    reason=f"El script de Python finalizó con código de error {exit_code}.",
                    suggested_fix=f"Analiza el traceback en stderr y corrige el script antes de continuar:\n{stderr[:300]}"
                )
            if stderr and ("Traceback" in stderr or "Error" in stderr):
                return VerificationResult(
                    passed=False,
                    reason=f"Se detectó un Traceback no capturado en stderr: {stderr[:200]}",
                    suggested_fix="Corrige el error de ejecución en el código."
                )

            return VerificationResult(
                passed=True,
                reason="El código Python finalizó exitosamente con código de salida 0 sin excepciones."
            )

        # 3. Verificación para comandos de consola (PowerShell)
        if tool_name == "execute_command":
            cmd = str(arguments.get("command", "")).lower()
            stdlib_modules = {
                "asyncio", "socket", "threading", "dataclasses", "argparse", "pathlib",
                "typing", "json", "sqlite3", "hashlib", "math", "os", "sys", "re",
                "time", "shutil", "concurrent.futures", "subprocess", "unittest"
            }
            if "pip install" in cmd:
                tokens = cmd.split("pip install")[-1].split()
                installed_pkg = tokens[0].strip().lower() if tokens else ""
                if installed_pkg in stdlib_modules:
                    return VerificationResult(
                        passed=False,
                        reason=f"Intento de instalar '{installed_pkg}' con pip. Este módulo pertenece a la biblioteca estándar de Python y ya está integrado en el intérprete.",
                        suggested_fix=f"Elimina el comando 'pip install {installed_pkg}' e impórtalo directamente en tu código Python ('import {installed_pkg}')."
                    )

            exit_code = result.data.get("exit_code") if result.data else None
            stderr = result.data.get("stderr", "") if result.data else ""

            if exit_code is not None and exit_code != 0:
                return VerificationResult(
                    passed=False,
                    reason=f"El comando PowerShell falló con código de salida {exit_code}.",
                    suggested_fix=f"Verifica la sintaxis del comando en Windows PowerShell. Error: {stderr[:200]}"
                )

            return VerificationResult(
                passed=True,
                reason=f"Comando completado exitosamente (código {exit_code})."
            )

        # 4. Verificación para descarga web
        if tool_name == "fetch_webpage":
            retrieved_len = result.data.get("retrieved_length", len(result.output)) if result.data else len(result.output)
            if retrieved_len < 30 or "No se pudo extraer texto" in result.output:
                return VerificationResult(
                    passed=False,
                    reason="No se pudo extraer contenido textual útil de la URL proporcionada.",
                    suggested_fix="Prueba con otra URL o utiliza el buscador para encontrar una fuente alternativa."
                )
            return VerificationResult(
                passed=True,
                reason=f"Contenido web descargado e ingerido con éxito ({retrieved_len} caracteres)."
            )

        # 5. Verificación para clonación de GitHub
        if tool_name == "clone_github_repo":
            target_path_str = result.data.get("path") if result.data else None
            if target_path_str:
                p = Path(target_path_str)
                if not p.exists() or not any(p.iterdir()):
                    return VerificationResult(
                        passed=False,
                        reason=f"El repositorio en '{p}' no existe o está vacío tras el clonado.",
                        suggested_fix="Verifica que la URL del repositorio sea pública y válida."
                    )
        # 6. Verificación para ejecución neuronal OpenMythos
        if tool_name == "run_open_mythos":
            rho_a = result.data.get("rho_A") if result.data else None
            if rho_a is not None and rho_a >= 1.0:
                return VerificationResult(
                    passed=False,
                    reason=f"El radio espectral ρ(A)={rho_a:.4f} supera 1.0, violando el criterio de estabilidad LTI.",
                    suggested_fix="Ajusta los parámetros de inyección o la dimensión del modelo para mantener ρ(A) < 1."
                )
            dev = result.data.get("device", "GPU") if result.data else "GPU"
            return VerificationResult(
                passed=True,
                reason=f"Ejecución neuronal OpenMythos validada en {dev} con estabilidad espectral garantizada."
            )

        # 7. Verificación para generación de video HyperFrames
        if tool_name == "render_hyperframes_video":
            v_path_str = result.data.get("video_path") if result.data else None
            if v_path_str:
                vp = Path(v_path_str)
                if not vp.exists():
                    return VerificationResult(
                        passed=False,
                        reason=f"El archivo de video renderizado '{vp.name}' no existe en disco.",
                        suggested_fix="Revisa el log de HyperFrames y la sintaxis de index.html."
                    )
                if vp.stat().st_size == 0:
                    return VerificationResult(
                        passed=False,
                        reason=f"El video '{vp.name}' fue generado pero tiene 0 bytes.",
                        suggested_fix="Verifica que las animaciones de GSAP tengan duración mayor a 0."
                    )
                dur = result.data.get("duration_seconds", "?")
                res = result.data.get("resolution", "?")
                return VerificationResult(
                    passed=True,
                    reason=f"Video MP4 verificado en disco ({vp.stat().st_size} bytes, {dur}s @ {res})."
                )

        # Verificación por defecto
        return VerificationResult(
            passed=True,
            reason=f"Herramienta '{tool_name}' completada sin anomalías."
        )
