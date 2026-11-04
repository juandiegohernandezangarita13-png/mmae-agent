"""
Módulo Duck Companion: Controlador y puente nativo del Pato de Escritorio para MMAE / JEV.
Reemplaza la antigua isla flotante por un compañero animado interactivo estilo pixel-art
que camina sobre la barra de tareas de Windows, muestra el estado del agente y abre la
interfaz principal al hacer doble clic.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import webview

from jev.core.status_sync import get_agent_status
from utils.logger import log

BASE_DIR = Path(__file__).resolve().parents[2]


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", wintypes.INT),
        ("cxRightWidth", wintypes.INT),
        ("cyTopHeight", wintypes.INT),
        ("cyBottomHeight", wintypes.INT),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def enable_dpi_awareness() -> None:
    """Configura DPI awareness para coordenadas estables en pantallas de alta resolución."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def screen_metrics() -> Tuple[float, float, float]:
    """Retorna (ancho_lógico, alto_lógico, escala) de la pantalla principal."""
    if sys.platform != "win32":
        return 1920.0, 1080.0, 1.0
    try:
        user32 = ctypes.windll.user32
        try:
            dpi = float(user32.GetDpiForSystem())
        except Exception:
            dpi = 96.0
        scale = max(1.0, dpi / 96.0)
        width = float(user32.GetSystemMetrics(0))
        height = float(user32.GetSystemMetrics(1))
        return width / scale, height / scale, scale
    except Exception:
        return 1920.0, 1080.0, 1.0


def compute_duck_position(width: int = 280, height: int = 200) -> Tuple[int, int]:
    """Calcula la posición para que el pato descanse exactamente encima de la barra de tareas de Windows."""
    if sys.platform != "win32":
        return 100, 100

    try:
        user32 = ctypes.windll.user32
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        # 0x00000001 = MONITOR_DEFAULTTOPRIMARY
        monitor = user32.MonitorFromWindow(0, 1)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            logical_w, logical_h, scale = screen_metrics()
            # Posicionar sobre el borde inferior del área de trabajo (justo encima de la taskbar)
            work_bottom_logical = work.bottom / scale
            work_right_logical = work.right / scale

            pos_x = int(work_right_logical - width - 60)
            pos_y = int(work_bottom_logical - height - 10)
            return max(20, pos_x), max(20, pos_y)
    except Exception:
        pass

    logical_w, logical_h, _ = screen_metrics()
    return int(logical_w - width - 60), int(logical_h - height - 60)


def apply_duck_transparency(hwnd: int, native_form: Any = None) -> None:
    """Configura transparencia total para WebView2 y Win32 (sin fondos blancos ni bordes)."""
    if sys.platform != "win32":
        return

    if native_form is not None:
        try:
            import clr
            clr.AddReference('System.Drawing')
            from System.Drawing import Color
            from System import Action

            def _fix():
                native_form.AllowTransparency = True
                native_form.BackColor = Color.FromArgb(0, 0, 0)
                native_form.TransparencyKey = Color.Empty
                if hasattr(native_form, "browser") and hasattr(native_form.browser, "webview"):
                    native_form.browser.webview.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0)

            if hasattr(native_form, "InvokeRequired") and native_form.InvokeRequired:
                native_form.Invoke(Action(_fix))
            else:
                _fix()
        except Exception:
            pass

    if hwnd:
        try:
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi

            # Quitar marco nativo y activar layered window
            style = user32.GetWindowLongW(hwnd, -16)
            style &= ~(0x00800000 | 0x00C00000 | 0x00040000)
            user32.SetWindowLongW(hwnd, -16, style)

            ex_style = user32.GetWindowLongW(hwnd, -20)
            ex_style &= ~(0x00000100 | 0x00000200 | 0x00020000 | 0x00000001 | 0x00040000)
            ex_style |= 0x00080000  # WS_EX_LAYERED
            ex_style |= 0x00000080  # WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, -20, ex_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

            # Composición DWM transparente
            margins = _MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass


class DuckBridge:
    """API bidireccional JavaScript <-> Python para el compañero Pato de Escritorio."""

    def __init__(self) -> None:
        self._duck_window = None
        self._main_window = None
        self._hwnd: Optional[int] = None

    def attach(self, duck_window, main_window=None) -> None:
        self._duck_window = duck_window
        self._main_window = main_window

    def set_native_handle(self, hwnd: int, native_form: Any = None) -> None:
        self._hwnd = hwnd
        apply_duck_transparency(hwnd, native_form)

    def get_status(self, *args, **kwargs) -> Dict[str, Any]:
        """Devuelve el estado de actividad del agente en tiempo real para la burbuja."""
        status = get_agent_status()
        return status

    def open_main(self, *args, **kwargs) -> Dict[str, Any]:
        """Abre o enfoca la interfaz principal de MMAE / JEV cuando se toca dos veces al pato."""
        log.info("🦆 [DesktopDuck]: ¡Doble clic recibido! Abriendo interfaz del agente...")

        # 1. Si existe la ventana en el mismo proceso, restaurarla y enfocarla
        if self._main_window is not None:
            try:
                self._main_window.show()
                restore = getattr(self._main_window, "restore", None)
                if callable(restore):
                    restore()
                native = getattr(self._main_window, "native", None)
                if native and hasattr(native, "Handle"):
                    h = int(native.Handle.ToInt64()) if hasattr(native.Handle, "ToInt64") else int(native.Handle)
                    ctypes.windll.user32.SetForegroundWindow(h)
                return {"ok": True, "focused": True}
            except Exception:
                pass

        # 2. Comprobar si ya existe una ventana abierta en el sistema y traerla al frente
        try:
            found_hwnd = None
            def _enum_win(h, _):
                nonlocal found_hwnd
                if ctypes.windll.user32.IsWindowVisible(h):
                    length = ctypes.windll.user32.GetWindowTextLengthW(h)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                        title = buff.value
                        if "MMAE" in title or "JARVIS" in title or "Bable" in title:
                            found_hwnd = h
                            return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_win), 0)

            if found_hwnd:
                ctypes.windll.user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(found_hwnd)
                ctypes.windll.user32.BringWindowToTop(found_hwnd)
                return {"ok": True, "brought_to_front": True}
        except Exception:
            pass

        # 3. Lanzar la aplicación principal de forma desacoplada
        try:
            launcher_script = BASE_DIR / "jev_launcher.py"
            app_script = BASE_DIR / "app.py"
            py_bin = sys.executable or "python.exe"

            cmd = [py_bin, str(launcher_script), "--classic"] if launcher_script.exists() else [py_bin, str(app_script)]
            DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                creationflags=DETACHED if sys.platform == "win32" else 0,
                close_fds=True,
            )
            return {"ok": True, "launched": True}
        except Exception as e:
            log.error(f"Error lanzando aplicación principal: {e}")
            return {"ok": False, "error": str(e)}

    def close_widget(self, *args, **kwargs) -> Dict[str, Any]:
        """Cierra el widget del pato."""
        if self._duck_window is not None:
            try:
                self._duck_window.destroy()
            except Exception:
                pass
        return {"ok": True}


__all__ = [
    "DuckBridge",
    "enable_dpi_awareness",
    "screen_metrics",
    "compute_duck_position",
    "apply_duck_transparency",
]
