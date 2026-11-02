"""
Herramienta de Supervisión y Recuperación de Ventanas y Procesos Congelados (Window Watchdog) para JEV.
Detecta ventanas en estado '(No responde)' mediante la API nativa de Windows (user32.IsHungAppWindow)
y permite al agente auto-recuperarse matando o reiniciando aplicaciones bloqueadas sin intervención manual.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
from typing import Dict, Any, List, Optional
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class WindowWatchdogTool(BaseTool):
    """Detecta ventanas que no responden ('No responde' / Hung) y las recupera o reinicia automáticamente."""
    name = "window_watchdog"
    description = (
        "Supervisa y repara aplicaciones congeladas en Windows. "
        "Usa 'check_hung' para detectar qué ventanas están en estado 'No responde', "
        "'kill_hung' para forzar el cierre de procesos colgados, y "
        "'restart_app' para cerrar y volver a abrir la aplicación limpia."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check_hung", "kill_hung", "restart_app"],
                "description": "Acción a realizar: 'check_hung', 'kill_hung', 'restart_app'.",
                "default": "check_hung"
            },
            "app_name": {
                "type": "string",
                "description": "Nombre o palabra clave de la aplicación objetivo (ej: 'openscad', 'blender', 'notepad', 'whatsapp')."
            }
        },
        "required": ["action"]
    }

    def execute(self, action: str = "check_hung", app_name: Optional[str] = None, **kwargs) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(success=False, output="", error="window_watchdog solo está implementado para Windows.")

        user32 = ctypes.windll.user32
        target_kw = (app_name or "").strip().lower()

        # -------------------------------------------------------------
        # 1. Encontrar ventanas congeladas
        # -------------------------------------------------------------
        hung_windows: List[Dict[str, Any]] = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _enum_proc(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                # Comprobar si la ventana está colgada
                is_hung = bool(user32.IsHungAppWindow(hwnd))
                length = user32.GetWindowTextLengthW(hwnd)
                title = ""
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                if title:
                    matches = True
                    if target_kw:
                        matches = target_kw in title.lower()

                    if is_hung and matches:
                        hung_windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": pid.value,
                            "is_hung": True
                        })
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)

        # Acción: check_hung
        if action == "check_hung":
            if not hung_windows:
                msg = f"✓ Todas las ventanas {'de ' + app_name if app_name else 'del sistema'} responden activamente. Cero bloqueos detectados."
                return ToolResult(success=True, output=msg, data={"hung_count": 0, "hung_windows": []})

            lines = [f"⚠️ Ventanas congeladas ('No responde') detectadas ({len(hung_windows)}):"]
            for w in hung_windows:
                lines.append(f"• PID {w['pid']}: '{w['title']}' (HWND: {w['hwnd']})")
            lines.append("Puedes usar action='kill_hung' o 'restart_app' para desbloquearlas.")
            return ToolResult(success=True, output="\n".join(lines), data={"hung_count": len(hung_windows), "hung_windows": hung_windows})

        # Acción: kill_hung
        elif action == "kill_hung":
            if not hung_windows:
                return ToolResult(success=True, output="No se encontraron ventanas congeladas que cerrar.", data={"killed": []})

            killed = []
            for w in hung_windows:
                pid = w["pid"]
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                    killed.append(w)
                except Exception as e:
                    pass

            return ToolResult(
                success=True,
                output=f"✓ Procesos colgados forzados a cerrar ({len(killed)}): " + ", ".join([f"'{k['title']}' (PID {k['pid']})" for k in killed]),
                data={"killed": killed}
            )

        # Acción: restart_app
        elif action == "restart_app":
            if not target_kw:
                return ToolResult(success=False, output="", error="Debes especificar 'app_name' (ej: 'openscad') para reiniciar.")

            # 1. Matar procesos existentes
            try:
                subprocess.run(["taskkill", "/F", "/IM", f"{target_kw}.exe"], capture_output=True, timeout=5)
            except Exception:
                pass

            time.sleep(1.0)

            # 2. Reabrir mediante open_application
            from jev.tools.system_apps import OpenApplicationTool
            opener = OpenApplicationTool()
            res = opener.execute(target=target_kw)

            if res.success:
                return ToolResult(
                    success=True,
                    output=f"✓ Aplicación '{target_kw}' cerrada forzosamente y reiniciada limpia.",
                    data={"restarted": target_kw}
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Se cerró la aplicación pero ocurrió un error al reiniciarla: {res.error}"
                )

        return ToolResult(success=False, output="", error=f"Acción '{action}' desconocida para window_watchdog.")
