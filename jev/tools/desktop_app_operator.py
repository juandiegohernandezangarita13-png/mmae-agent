"""
Herramienta Universal de Control de Aplicaciones de Escritorio y Mecanografía en Vivo (Live Operator).
Permite al agente abrir cualquier aplicación (OpenSCAD, Notepad, VS Code, Blender, etc.),
traerla al frente con foco absoluto de Windows y escribir código o texto simulando el teclado
en tiempo real frente al usuario, finalizando con atajos de compilación/ejecución (ej. F5 en OpenSCAD).

IMPLEMENTACIÓN 100% CTYPES: Cero dependencias externas de win32gui/pywin32.
Funciona en cualquier intérprete de Python en Windows.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import shutil
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Any, List, Optional

import pyautogui
from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config

# Configuración de seguridad PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


class DesktopAppLiveOperatorTool(BaseTool):
    """
    Controlador universal de aplicaciones de escritorio: abre la ventana,
    toma el foco y escribe directamente en el editor con simulación de teclado en vivo.
    """
    name = "desktop_app_live_type"
    description = (
        "Abre cualquier aplicación de escritorio en Windows (ej: 'openscad', 'notepad', 'vscode', 'blender'), "
        "la enfoca al frente y escribe código o texto directamente en la zona activa de edición usando el teclado "
        "en tiempo real. Puede pulsar atajos automáticos al finalizar (ej: ['f5'] para compilar en OpenSCAD o "
        "['ctrl', 's'] para guardar)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "Nombre de la aplicación ('openscad', 'notepad', 'vscode', 'code', 'blender', 'calc') o ruta al .exe."
            },
            "code": {
                "type": "string",
                "description": "El código, texto o instrucciones que se escribirán directamente con el teclado en la aplicación."
            },
            "description": {
                "type": "string",
                "description": "Breve descripción humana de lo que se está creando (ej: 'Soporte 3D de audífonos', 'Script de análisis')."
            },
            "new_document": {
                "type": "boolean",
                "description": "Si es True (defecto), presiona Ctrl+N al enfocar para asegurar un documento o buffer en blanco.",
                "default": True
            },
            "clear_existing": {
                "type": "boolean",
                "description": "Si es True, presiona Ctrl+A y Backspace para limpiar el editor existente antes de escribir.",
                "default": False
            },
            "typing_speed": {
                "type": "number",
                "description": "Segundos entre pulsaciones de tecla (ej: 0.01 para efecto mecanografía humana visible; 0.0 para pegado rápido).",
                "default": 0.01
            },
            "post_keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de teclas o atajos a pulsar al terminar de escribir (ej: ['f5'] para OpenSCAD, ['ctrl', 's'] para guardar, ['alt', 'p'] para Blender).",
                "default": ["f5"]
            },
            "wait_after_launch": {
                "type": "number",
                "description": "Segundos de espera tras lanzar la aplicación para que la ventana cargue completamente (defecto 2.0).",
                "default": 2.0
            }
        },
        "required": ["app", "code"]
    }

    # Mapa de aplicaciones conocidas y sus ejecutables / títulos típicos
    KNOWN_APPS: Dict[str, Dict[str, Any]] = {
        "openscad": {
            "paths": [
                r"C:\Program Files\OpenSCAD\openscad.exe",
                r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
            ],
            "title_match": "openscad",
            "default_post_keys": ["f5"],  # Compilar y Renderizar en visor 3D
        },
        "notepad": {
            "paths": [r"notepad.exe", r"C:\Windows\notepad.exe", r"C:\Windows\System32\notepad.exe"],
            "title_match": "notepad",
            "default_post_keys": ["ctrl", "s"],
        },
        "bloc de notas": {
            "paths": [r"notepad.exe"],
            "title_match": "bloc de notas",
            "default_post_keys": ["ctrl", "s"],
        },
        "vscode": {
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                "code.cmd",
            ],
            "title_match": "visual studio code",
            "default_post_keys": ["ctrl", "s"],
        },
        "code": {
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                "code.cmd",
            ],
            "title_match": "visual studio code",
            "default_post_keys": ["ctrl", "s"],
        },
        "blender": {
            "paths": [
                r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender\blender.exe",
            ],
            "title_match": "blender",
            "default_post_keys": ["alt", "p"],
        },
        "calc": {
            "paths": [r"calc.exe"],
            "title_match": "calculadora",
            "default_post_keys": [],
        }
    }

    def _resolve_executable(self, app_name: str) -> Optional[str]:
        """Encuentra la ruta completa del ejecutable o identificador en el sistema."""
        normalized = (app_name or "").strip().lower()

        # Si el usuario pasó una ruta que existe directamente
        if os.path.isfile(app_name):
            return str(Path(app_name).resolve())

        # Si es un alias conocido
        info = self.KNOWN_APPS.get(normalized)
        if info:
            for p in info["paths"]:
                if os.path.isfile(p):
                    return p
                found_in_path = shutil.which(p)
                if found_in_path:
                    return found_in_path

        # Búsqueda en PATH de Windows
        which_result = shutil.which(app_name) or shutil.which(f"{app_name}.exe")
        if which_result:
            return which_result

        # Catálogo StartApps de Windows (UWP, Store, Atajos instalados)
        try:
            from jev.tools.system_apps import OpenApplicationTool
            start_apps = OpenApplicationTool._get_start_apps()
            if normalized in start_apps:
                return f"shell:AppsFolder\\{start_apps[normalized]}"
            for name, app_id in start_apps.items():
                if normalized in name or any(w in name for w in normalized.split() if len(w) > 2):
                    return f"shell:AppsFolder\\{app_id}"
        except Exception:
            pass

        # Búsqueda aproximada en Program Files para apps típicas
        prog_files = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                      os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                      os.path.expandvars(r"%LOCALAPPDATA%\Programs")]
        for pf in prog_files:
            candidate = Path(pf) / app_name / f"{app_name}.exe"
            if candidate.exists():
                return str(candidate)

        return None

    def _find_window_hwnd(self, title_keyword: str) -> Optional[int]:
        """Localiza el HWND de una ventana visible usando ctypes (cero dependencias de win32gui)."""
        if sys.platform != "win32":
            return None

        user32 = ctypes.windll.user32
        keyword = title_keyword.lower()
        found_hwnds: List[int] = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _enum_proc(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if keyword in buf.value.lower():
                        found_hwnds.append(hwnd)
            return True

        try:
            user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
        except Exception:
            pass

        return found_hwnds[0] if found_hwnds else None

    def _get_window_title(self, hwnd: int) -> str:
        """Obtiene el título de la ventana usando ctypes."""
        if not hwnd or sys.platform != "win32":
            return ""
        try:
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value
        except Exception:
            pass
        return ""

    def _force_foreground(self, hwnd: int) -> bool:
        """Fuerza a Windows a traer la ventana especificada al frente y darle foco activo vía ctypes."""
        if sys.platform != "win32" or not hwnd:
            return False

        try:
            user32 = ctypes.windll.user32
            SW_RESTORE = 9

            # Restaurar si estaba minimizada
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.1)

            # Técnica de bypass de foco de Windows mediante AttachThreadInput
            current_fg = user32.GetForegroundWindow()
            if current_fg and current_fg != hwnd:
                try:
                    fg_thread = user32.GetWindowThreadProcessId(current_fg, None)
                    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
                    if fg_thread != target_thread:
                        user32.AttachThreadInput(fg_thread, target_thread, True)
                        user32.BringWindowToTop(hwnd)
                        user32.SetForegroundWindow(hwnd)
                        user32.AttachThreadInput(fg_thread, target_thread, False)
                    else:
                        user32.BringWindowToTop(hwnd)
                        user32.SetForegroundWindow(hwnd)
                except Exception:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)

            time.sleep(0.2)
            return True
        except Exception as e:
            print(f"[DesktopAppLiveOperatorTool] Error forzando foco: {e}")
            return False

    def execute(
        self,
        app: str,
        code: str,
        description: str = "",
        new_document: bool = True,
        clear_existing: bool = False,
        typing_speed: float = 0.01,
        post_keys: Optional[List[str]] = None,
        wait_after_launch: float = 2.0,
        **kwargs
    ) -> ToolResult:
        if not app or not code:
            return ToolResult(
                success=False,
                output="",
                error="Debes proporcionar 'app' (ej: 'openscad', 'notepad') y 'code' a escribir."
            )

        if sys.platform != "win32":
            return ToolResult(
                success=False,
                output="",
                error="El control de teclado y ventanas de escritorio en vivo solo está implementado para Windows."
            )

        app_clean = app.strip()
        exe_path = self._resolve_executable(app_clean)
        known_info = self.KNOWN_APPS.get(app_clean.lower(), {})
        title_keyword = known_info.get("title_match", app_clean.lower())

        # Si post_keys no se especificó y la app tiene defaults (ej: F5 en OpenSCAD)
        if post_keys is None:
            post_keys = known_info.get("default_post_keys", ["f5"] if "openscad" in app_clean.lower() else [])

        # 1. Comprobar si la ventana ya está abierta
        hwnd = self._find_window_hwnd(title_keyword)
        app_was_already_running = hwnd is not None

        if not hwnd:
            if not exe_path:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No se pudo encontrar el ejecutable para la aplicación '{app}'. Asegúrate de que esté instalada o indica la ruta completa."
                )

            # Lanzar la aplicación en proceso independiente
            try:
                if exe_path.startswith("shell:"):
                    ctypes.windll.shell32.ShellExecuteW(None, "open", exe_path, None, None, 1)
                else:
                    subprocess.Popen([exe_path], shell=False)
            except Exception as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fallo al abrir ejecutable '{exe_path}': {e}"
                )

            # Esperar a que la ventana aparezca (hasta max_wait segundos)
            start_time = time.time()
            max_wait = max(3.0, float(wait_after_launch))
            while time.time() - start_time < max_wait:
                time.sleep(0.4)
                hwnd = self._find_window_hwnd(title_keyword)
                if hwnd:
                    break

        if not hwnd:
            return ToolResult(
                success=False,
                output="",
                error=f"La aplicación '{app}' se inició pero no se detectó su ventana en pantalla."
            )

        # 2. Traer la ventana al frente y forzar foco
        self._force_foreground(hwnd)
        time.sleep(0.5)

        # 3. Preparar el espacio de edición
        try:
            if new_document and not clear_existing:
                pyautogui.hotkey("ctrl", "n")
                time.sleep(0.3)
            elif clear_existing:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)

            # 4. Escribir el código en la pantalla simulando el teclado
            lines = code.splitlines()
            total_lines = len(lines)

            # Mover cursor fuera de la esquina para evitar FailSafe prematuro
            cx, cy = pyautogui.position()
            if cx < 20 and cy < 20:
                pyautogui.moveTo(200, 200)

            for idx, line in enumerate(lines):
                if typing_speed > 0:
                    if len(line) <= 80:
                        pyautogui.write(line, interval=max(0.001, typing_speed))
                    else:
                        import pyperclip
                        pyperclip.copy(line)
                        time.sleep(0.01)
                        pyautogui.hotkey("ctrl", "v")
                else:
                    import pyperclip
                    pyperclip.copy(line)
                    time.sleep(0.01)
                    pyautogui.hotkey("ctrl", "v")

                if idx < total_lines - 1:
                    pyautogui.press("enter")
                    time.sleep(0.01)

            time.sleep(0.4)

            # 5. Ejecutar teclas posteriores (ej: F5 para compilar en OpenSCAD)
            keys_executed: List[str] = []
            if post_keys:
                time.sleep(0.3)
                for pk in post_keys:
                    k = str(pk).strip().lower()
                    if k:
                        pyautogui.press(k)
                        keys_executed.append(k)
                        time.sleep(0.2)

            window_title = self._get_window_title(hwnd) or app
            summary_msg = (
                f"✅ Aplicación '{app}' operada exitosamente.\n"
                f"• Ventana: '{window_title}'\n"
                f"• Líneas escritas en vivo: {total_lines} ({len(code)} caracteres)\n"
                f"• Atajos posteriores pulsados: {keys_executed or 'Ninguno'}\n"
                f"• Descripción: {description or 'Mecanografía directa completada'}"
            )

            return ToolResult(
                success=True,
                output=summary_msg,
                data={
                    "app": app,
                    "exe_path": exe_path,
                    "window_title": window_title,
                    "lines_count": total_lines,
                    "char_count": len(code),
                    "post_keys": keys_executed,
                    "description": description,
                    "already_running": app_was_already_running,
                }
            )

        except pyautogui.FailSafeException:
            return ToolResult(
                success=False,
                output="",
                error="Parada de emergencia (FailSafe activado): Se detectó el cursor en una esquina de la pantalla. Mecanografía abortada con seguridad."
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error durante la mecanografía en '{app}': {e}"
            )
