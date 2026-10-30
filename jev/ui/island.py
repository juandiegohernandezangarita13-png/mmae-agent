"""
Isla de escritorio de JEV: el compañero flotante que vive en la parte superior
de la pantalla, al estilo de la isla de Coucou.

Responsabilidades:
  * Exponer a la página island.html el estado del agente (polling ligero).
  * Redimensionar la ventana entre el modo píldora y el panel expandido.
  * Reabrir la ventana completa de JARVIS bajo demanda.
  * Canalizar aprobaciones de acciones sensibles (permitir / denegar).
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

import webview

#: Tamaño lógico de la ventana en modo píldora y en modo panel.
COLLAPSED_SIZE = (232, 66)
EXPANDED_SIZE = (474, 386)


import ctypes
from ctypes import wintypes

# --- Win32: geometría en píxeles físicos (inmune a la ambigüedad DPI) ------
_HWND_TOPMOST = -1
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_SW_SHOWNOACTIVATE = 4
_MONITOR_DEFAULTTONEAREST = 2


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def enable_dpi_awareness() -> None:
    """Declara el proceso DPI-aware antes de crear ventanas (coordenadas estables)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def screen_metrics() -> tuple[float, float, float]:
    """Devuelve (ancho_lógico, alto_lógico, escala) de la pantalla principal."""
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
        return 1280.0, 800.0, 1.0


def compute_position(width: int, height: int = 0) -> tuple[int, int]:
    """Posición lógica inicial (se corrige luego con píxeles físicos)."""
    logical_w, _, _ = screen_metrics()
    x = int(max(0, (logical_w - width) / 2))
    return x, 0


def _window_geometry(hwnd: int, width: int, height: int) -> tuple[int, int, int, int]:
    """Calcula y aplica tamaño/posición físicos, centrados en el monitor."""
    user32 = ctypes.windll.user32
    try:
        dpi = float(user32.GetDpiForWindow(hwnd))
    except Exception:
        dpi = 96.0
    scale = max(1.0, dpi / 96.0)
    phys_w = max(1, int(round(width * scale)))
    phys_h = max(1, int(round(height * scale)))

    monitor = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        work = info.rcWork
        work_w = work.right - work.left
        x = work.left + max(0, (work_w - phys_w) // 2)
        y = work.top
    else:
        x = max(0, (user32.GetSystemMetrics(0) - phys_w) // 2)
        y = 0

    user32.SetWindowPos(hwnd, _HWND_TOPMOST, x, y, phys_w, phys_h,
                        _SWP_NOACTIVATE | _SWP_SHOWWINDOW)
    return x, y, phys_w, phys_h


class IslandBridge:
    """API JavaScript <-> Python de la isla flotante."""

    def __init__(self) -> None:
        self._jarvis = None
        self._main_window = None
        self._island_window = None
        self._expanded = False
        self._quit_state: Optional[Dict[str, bool]] = None
        self._hwnd: Optional[int] = None

    # ------------------------------------------------------------------
    # Conexión con el resto de la aplicación
    # ------------------------------------------------------------------
    def attach(self, jarvis, main_window, island_window, quit_state: Optional[Dict[str, bool]] = None) -> None:
        self._jarvis = jarvis
        self._main_window = main_window
        self._island_window = island_window
        self._quit_state = quit_state
        if jarvis is not None:
            jarvis._island_mode = True

    # ------------------------------------------------------------------
    # API expuesta al frontend
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        if self._jarvis is None:
            return {
                "state": "idle",
                "thought": "",
                "tool": "",
                "tool_args": "",
                "tool_in_progress": False,
                "last_ok": None,
                "task": "",
                "voice": False,
                "confirm_risky": False,
                "pending": None,
                "cpu": 0,
                "ram": 0,
                "model": "—",
                "island_mode": True,
            }
        return self._jarvis.activity_snapshot()

    def expand(self) -> Dict[str, Any]:
        self._layout(expanded=True)
        return {"ok": True, "expanded": True}

    def collapse(self) -> Dict[str, Any]:
        self._layout(expanded=False)
        return {"ok": True, "expanded": False}

    def open_main(self) -> Dict[str, Any]:
        """Muestra y enfoca la ventana completa de JARVIS."""
        if self._main_window is None:
            return {"ok": False, "error": "La ventana principal no está disponible."}
        try:
            self._main_window.show()
            restore = getattr(self._main_window, "restore", None)
            if callable(restore):
                restore()
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - depende de la GUI
            return {"ok": False, "error": str(exc)}

    def stop_agent(self) -> Dict[str, Any]:
        if self._jarvis is None:
            return {"ok": False}
        self._jarvis.stop_agent()
        return {"ok": True}

    def toggle_voice(self) -> Dict[str, Any]:
        if self._jarvis is None:
            return {"ok": False, "enabled": False}
        enabled = not bool(getattr(self._jarvis, "_voice_enabled", False))
        self._jarvis.toggle_voice_synthesis(enabled)
        return {"ok": True, "enabled": enabled}

    def set_confirm_risky(self, enabled: bool = False) -> Dict[str, Any]:
        if self._jarvis is None:
            return {"ok": False}
        value = self._jarvis.set_confirm_risky(bool(enabled))
        return {"ok": True, "enabled": value}

    def resolve_approval(self, allow: bool = False) -> Dict[str, Any]:
        if self._jarvis is None:
            return {"ok": False}
        return self._jarvis.resolve_approval(bool(allow))

    def send_chat(self, text: str) -> Dict[str, Any]:
        """Envía un prompt o tarea directamente a JEV desde la isla flotante."""
        if not text or not str(text).strip():
            return {"ok": False, "error": "Prompt vacío"}
        if self._jarvis is None:
            return {"ok": False, "error": "JEV no está conectado"}
        try:
            threading.Thread(
                target=self._jarvis.execute_task,
                args=(str(text).strip(),),
                daemon=True
            ).start()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def send_file_drop(self, filename: str, file_data: str = "", prompt: str = "") -> Dict[str, Any]:
        """Procesa un archivo o imagen arrastrado sobre la isla flotante."""
        if self._jarvis is None:
            return {"ok": False, "error": "JEV no está conectado"}
        try:
            task_desc = str(prompt).strip() if prompt else f"Analiza y describe este archivo: {filename}"
            if file_data and str(file_data).startswith("data:image"):
                threading.Thread(
                    target=self._jarvis.execute_task_with_image,
                    args=(task_desc, file_data),
                    daemon=True
                ).start()
            else:
                threading.Thread(
                    target=self._jarvis.execute_task,
                    args=(f"{task_desc}\n[Archivo adjunto: {filename}]",),
                    daemon=True
                ).start()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_chat_history(self) -> Dict[str, Any]:
        """Devuelve los mensajes recientes de la conversación activa."""
        if self._jarvis is None or not hasattr(self._jarvis, "_agent"):
            return {"ok": True, "messages": []}
        msgs = []
        try:
            raw = getattr(self._jarvis._agent, "messages", []) or []
            for m in raw[-20:]:
                role = m.get("role", "")
                content = m.get("content", "")
                if role in ("user", "assistant") and content:
                    msgs.append({"role": role, "content": str(content)[:600]})
        except Exception:
            pass
        return {"ok": True, "messages": msgs}

    def quit_app(self) -> Dict[str, Any]:
        """Cierra el agente y todas las ventanas de JEV."""
        if self._quit_state is not None:
            self._quit_state["quitting"] = True
        try:
            if self._jarvis is not None:
                self._jarvis.stop_agent()
        except Exception:
            pass
        try:
            for window in list(webview.windows):
                window.destroy()
        except Exception:
            pass
        return {"ok": True}

    # ------------------------------------------------------------------
    # Geometría / ventana
    # ------------------------------------------------------------------
    def set_native_handle(self, hwnd: Any) -> None:
        """Registra el HWND real y aplica la geometría en píxeles físicos."""
        try:
            if hasattr(hwnd, "ToInt64"):
                self._hwnd = int(hwnd.ToInt64())
            elif hasattr(hwnd, "ToInt32"):
                self._hwnd = int(hwnd.ToInt32())
            else:
                self._hwnd = int(str(hwnd))
            self._layout(self._expanded)
        except Exception:
            pass

    def _layout(self, expanded: bool) -> None:
        self._expanded = expanded
        width, height = EXPANDED_SIZE if expanded else COLLAPSED_SIZE

        if self._hwnd:
            try:
                _window_geometry(self._hwnd, width, height)
                return
            except Exception:
                pass

        if self._island_window is None:
            return
        x, y = compute_position(width)
        try:
            self._island_window.resize(width, height)
            self._island_window.move(x, y)
        except Exception:
            pass
