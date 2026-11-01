"""
Herramienta de apertura de aplicaciones y URI de Windows sin bloqueo.

Sustituye el patrón peligroso ``execute_command("notepad")``: ese comando deja a
PowerShell esperando a que la app se cierre y, al vencer el timeout, el runtime
mata el árbol de procesos completo (la app recién abierta se cierra sola).
``ShellExecuteW`` lanza la app y retorna inmediatamente, sin heredar stdio.
"""
from __future__ import annotations

import ctypes
import sys
from typing import Optional

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class OpenApplicationTool(BaseTool):
    """Abre una aplicación, documento o protocolo (whatsapp:, ms-settings:, https:)."""

    name = "open_application"
    description = (
        "Abre una aplicación, archivo o URI en Windows y retorna de inmediato, sin esperar "
        "a que la ventana se cierre. Usa target='notepad', target='whatsapp:' o una ruta/URL. "
        "Es la forma correcta de abrir apps; NO uses execute_command para lanzar ventanas."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Ejecutable, ruta de archivo o URI a abrir (ej: 'notepad', 'whatsapp:', 'https://...')."
            },
            "arguments": {
                "type": "string",
                "description": "Argumentos opcionales para el ejecutable (opcional)."
            }
        },
        "required": ["target"]
    }

    def execute(self, target: str, arguments: Optional[str] = None, **kwargs) -> ToolResult:
        target = (target or "").strip()
        if not target:
            return ToolResult(success=False, output="", error="Target vacío: indica qué aplicación o URI abrir.")

        if sys.platform != "win32":
            return ToolResult(success=False, output="", error="open_application solo está implementado para Windows.")

        try:
            shell32 = ctypes.windll.shell32
            shell32.ShellExecuteW.restype = ctypes.c_void_p
            result = shell32.ShellExecuteW(
                None,
                "open",
                target,
                arguments if arguments else None,
                str(default_config.workspace_dir),
                1,  # SW_SHOWNORMAL
            )
            code = int(result or 0)
            if code <= 32:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Windows no pudo abrir '{target}' (ShellExecuteW código {code}).",
                )
            return ToolResult(
                success=True,
                output=f"Aplicación/URI lanzada sin bloqueo: {target}"
                       + (f" (args: {arguments})" if arguments else ""),
                data={"target": target, "arguments": arguments, "shell_execute_code": code},
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"Error abriendo '{target}': {exc}")
