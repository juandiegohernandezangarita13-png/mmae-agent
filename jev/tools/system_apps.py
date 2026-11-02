"""
Herramienta Universal de Apertura de Aplicaciones, Archivos y Protocolos de Windows (OpenApplicationTool).

Sustituye el patrón peligroso ``execute_command("notepad")``: ese comando deja a
PowerShell esperando a que la app se cierre y, al vencer el timeout, el runtime
mata el árbol de procesos completo (la app recién abierta se cierra sola).

Incluye resolución inteligente mediante:
  1. Protocolos URI (whatsapp:, spotify:, calc:, ms-settings:)
  2. Catálogo StartApps (Get-StartApps / shell:AppsFolder) para apps de Windows Store y Win32
  3. Ejecutables nativos en PATH y carpetas de instalación estándar
  4. ShellExecuteW sin bloqueo
"""
from __future__ import annotations

import os
import sys
import shutil
import ctypes
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class OpenApplicationTool(BaseTool):
    """Abre cualquier aplicación, archivo o URI en Windows sin bloquear el hilo del agente."""

    name = "open_application"
    description = (
        "Abre cualquier aplicación, documento o URI en Windows de forma asíncrona sin bloquearse. "
        "Reconoce nombres comunes ('whatsapp', 'openscad', 'blender', 'spotify', 'vscode', 'notepad', 'calc'), "
        "rutas de archivo o enlaces web. Es la forma segura y oficial de abrir programas."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Nombre de la aplicación ('whatsapp', 'openscad', 'blender', 'calc', 'notepad'), ruta a un archivo o URI."
            },
            "arguments": {
                "type": "string",
                "description": "Argumentos opcionales para el ejecutable (opcional)."
            }
        },
        "required": ["target"]
    }

    _start_apps_cache: Optional[Dict[str, str]] = None

    @classmethod
    def _get_start_apps(cls) -> Dict[str, str]:
        """Obtiene y cachea el mapa de nombres de aplicaciones a AppIDs de Windows."""
        if cls._start_apps_cache is not None:
            return cls._start_apps_cache

        apps = {}
        try:
            ps_cmd = 'Get-StartApps | ForEach-Object { "$($_.Name)|$($_.AppID)" }'
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace"
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if "|" in line:
                        name, app_id = line.split("|", 1)
                        apps[name.strip().lower()] = app_id.strip()
        except Exception:
            pass

        cls._start_apps_cache = apps
        return apps

    def execute(self, target: str, arguments: Optional[str] = None, **kwargs) -> ToolResult:
        target = (target or "").strip()
        if not target:
            return ToolResult(success=False, output="", error="Target vacío: indica qué aplicación o URI abrir.")

        if sys.platform != "win32":
            return ToolResult(success=False, output="", error="open_application solo está implementado para Windows.")

        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.restype = ctypes.c_void_p

        # 1. Si es URL o ya tiene protocolo (contiene "://" o termina en ":")
        if "://" in target or (target.endswith(":") and len(target) > 2) or os.path.exists(target):
            res = shell32.ShellExecuteW(None, "open", target, arguments or None, str(default_config.workspace_dir), 1)
            code = int(res or 0)
            if code > 32:
                return ToolResult(success=True, output=f"✓ Lanzado exitosamente: {target}", data={"target": target, "code": code})

        # 2. Intentar ShellExecute directo (funciona para ejecutables en PATH como 'notepad', 'calc', 'cmd')
        res = shell32.ShellExecuteW(None, "open", target, arguments or None, str(default_config.workspace_dir), 1)
        code = int(res or 0)
        if code > 32:
            return ToolResult(success=True, output=f"✓ Aplicación lanzada: {target}", data={"target": target, "code": code})

        # 3. Intentar con protocolo URI común (ej: 'whatsapp' -> 'whatsapp:')
        protocol_cand = f"{target.lower()}:"
        res_proto = shell32.ShellExecuteW(None, "open", protocol_cand, arguments or None, str(default_config.workspace_dir), 1)
        if int(res_proto or 0) > 32:
            return ToolResult(success=True, output=f"✓ Aplicación abierta vía protocolo URI '{protocol_cand}'.", data={"target": protocol_cand})

        # 4. Búsqueda en el catálogo StartApps (UWP y aplicaciones instaladas)
        start_apps = self._get_start_apps()
        t_lower = target.lower()
        matched_id = None

        # Búsqueda exacta
        if t_lower in start_apps:
            matched_id = start_apps[t_lower]
        else:
            # Búsqueda por subcadena
            for app_name, app_id in start_apps.items():
                if t_lower in app_name or any(w in app_name for w in t_lower.split() if len(w) > 2):
                    matched_id = app_id
                    break

        if matched_id:
            try:
                # Lanzar mediante shell:AppsFolder\<AppID>
                app_path = f"shell:AppsFolder\\{matched_id}"
                res_app = shell32.ShellExecuteW(None, "open", app_path, arguments or None, None, 1)
                if int(res_app or 0) > 32:
                    return ToolResult(
                        success=True,
                        output=f"✓ Aplicación '{target}' localizada en catálogo de Windows y lanzada ({matched_id}).",
                        data={"target": target, "app_id": matched_id}
                    )
                # Fallback con explorer
                subprocess.Popen(["explorer.exe", app_path], shell=False)
                return ToolResult(
                    success=True,
                    output=f"✓ Aplicación '{target}' iniciada mediante Explorer ShellAppsFolder ({matched_id}).",
                    data={"target": target, "app_id": matched_id}
                )
            except Exception as e:
                pass

        # 5. Búsqueda en rutas de instalación habituales
        candidate_paths = [
            rf"C:\Program Files\{target}\{target}.exe",
            rf"C:\Program Files (x86)\{target}\{target}.exe",
            os.path.expandvars(rf"%LOCALAPPDATA%\Programs\{target}\{target}.exe"),
            os.path.expandvars(rf"%APPDATA%\{target}\{target}.exe"),
        ]
        for p in candidate_paths:
            if os.path.isfile(p):
                res_path = shell32.ShellExecuteW(None, "open", p, arguments or None, None, 1)
                if int(res_path or 0) > 32:
                    return ToolResult(success=True, output=f"✓ Aplicación iniciada desde '{p}'.", data={"path": p})

        return ToolResult(
            success=False,
            output="",
            error=f"Windows no pudo encontrar ni abrir la aplicación o recurso '{target}'. Verifica si está instalada."
        )
