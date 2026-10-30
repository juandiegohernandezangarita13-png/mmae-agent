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
COLLAPSED_SIZE = (232, 54)
EXPANDED_SIZE = (474, 340)


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


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


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


def apply_window_transparency(hwnd: int, native_form: Any = None) -> None:
    """Configura transparencia total a nivel WinForms, WebView2 y DWM (sin bordes ni cajas blancas)."""
    if native_form is not None:
        try:
            import clr
            clr.AddReference('System.Drawing')
            from System.Drawing import Color
            from System import Action

            def _fix():
                native_form.AllowTransparency = True
                native_form.BackColor = Color.FromArgb(0, 0, 0)
                native_form.TransparencyKey = Color.FromArgb(0, 0, 0)
                # Si WebView2 está disponible, forzar fondo 100% transparente sin halo blanco
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

            # 1. Quitar estilos de marco nativo (border, caption, 3d edge)
            style = user32.GetWindowLongW(hwnd, -16)
            style &= ~(0x00800000 | 0x00C00000 | 0x00040000)
            user32.SetWindowLongW(hwnd, -16, style)

            ex_style = user32.GetWindowLongW(hwnd, -20)
            ex_style &= ~(0x00000100 | 0x00000200 | 0x00020000 | 0x00000001 | 0x00040000)
            ex_style |= 0x00080000  # WS_EX_LAYERED
            ex_style |= 0x00000080  # WS_EX_TOOLWINDOW (oculta ventana flotante de la barra de tareas)
            user32.SetWindowLongW(hwnd, -20, ex_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

            # 2. Desactivar bordes nativos DWM de Windows 11
            val_corner = ctypes.c_int(1)  # DWMWCP_DONOTROUND
            dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(val_corner), ctypes.sizeof(val_corner))
            val_border = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
            dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(val_border), ctypes.sizeof(val_border))

            # 3. Composición DWM de cristal en toda el área
            margins = _MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass


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


def _window_geometry(hwnd: int, width: int, height: int, preserve_position: bool = True) -> tuple[int, int, int, int]:
    """Calcula y aplica tamaño/posición físicos, preservando la posición arrastrada por el usuario."""
    user32 = ctypes.windll.user32
    try:
        dpi = float(user32.GetDpiForWindow(hwnd))
    except Exception:
        dpi = 96.0
    scale = max(1.0, dpi / 96.0)
    phys_w = max(1, int(round(width * scale)))
    phys_h = max(1, int(round(height * scale)))

    # Consultar posición física actual
    rect = _RECT()
    has_pos = bool(user32.GetWindowRect(hwnd, ctypes.byref(rect)))

    monitor = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        work = info.rcWork
        work_w = work.right - work.left
        work_h = work.bottom - work.top
        # Si el usuario ya arrastró la ventana (no está en 0,0 por defecto), mantener su centro X y su Y
        if preserve_position and has_pos and (rect.right > rect.left) and (rect.bottom > rect.top) and (rect.left != 0 or rect.top != 0):
            curr_center_x = (rect.left + rect.right) // 2
            x = max(work.left, min(work.right - phys_w, curr_center_x - (phys_w // 2)))
            y = max(work.top, min(work.bottom - phys_h, rect.top))
        else:
            x = work.left + max(0, (work_w - phys_w) // 2)
            y = work.top
    else:
        x = max(0, (user32.GetSystemMetrics(0) - phys_w) // 2)
        y = 0

    user32.SetWindowPos(hwnd, _HWND_TOPMOST, x, y, phys_w, phys_h,
                        _SWP_NOACTIVATE | _SWP_SHOWWINDOW)
    _apply_rounded_region(hwnd, phys_w, phys_h, scale)
    return x, y, phys_w, phys_h


def _apply_rounded_region(hwnd: int, phys_w: int, phys_h: int, scale: float) -> None:
    """Recorta la ventana a la silueta visible (píldora o panel redondeado).

    Todo lo que quede fuera de la forma deja de existir para Windows, así que no
    puede aparecer ningún píxel gris/blanco del formulario en las esquinas.
    """
    try:
        gdi32 = ctypes.windll.gdi32
        collapsed_h = int(round(COLLAPSED_SIZE[1] * scale))
        if phys_h <= collapsed_h + 2:
            diameter = phys_h  # píldora: extremos totalmente redondos
        else:
            diameter = int(round(48 * scale))  # panel: radio 24px
        rgn = gdi32.CreateRoundRectRgn(0, 0, phys_w + 1, phys_h + 1, diameter, diameter)
        if rgn:
            # El sistema toma posesión de la región: no hay que liberarla.
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def setup_startup_launcher(enable: bool = True) -> bool:
    """Configura el inicio automático silencioso de JEV Island al encender la laptop."""
    try:
        import os
        from pathlib import Path

        appdata = os.environ.get("APPDATA")
        if not appdata:
            return False
        startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not startup_dir.exists():
            return False

        vbs_path = startup_dir / "iniciar_jev_isla.vbs"
        if not enable:
            if vbs_path.exists():
                vbs_path.unlink()
            return True

        repo_dir = Path(__file__).resolve().parent.parent.parent
        bat_path = repo_dir / "iniciar.bat"
        if not bat_path.exists():
            return False

        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\r\n'
            f'WshShell.CurrentDirectory = "{repo_dir}"\r\n'
            f'WshShell.Run """{bat_path}""", 0, False\r\n'
        )
        vbs_path.write_text(vbs_content, encoding="utf-8")
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    try:
        import os
        from pathlib import Path
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return False
        vbs_path = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "iniciar_jev_isla.vbs"
        return vbs_path.exists()
    except Exception:
        return False


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
        self._safe_eval_js("if(typeof setExpandedUI==='function') setExpandedUI(false);")
        return {"ok": True, "expanded": False}

    def drag_window(self) -> Dict[str, Any]:
        """Permite mover y arrastrar la ventana sin bordes por toda la pantalla usando Win32."""
        if not self._hwnd:
            return {"ok": False}
        try:
            ctypes.windll.user32.ReleaseCapture()
            # WM_SYSCOMMAND (0x0112), SC_MOVE + HTCAPTION (0xF012)
            ctypes.windll.user32.SendMessageW(self._hwnd, 0x0112, 0xF012, 0)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def is_autostart(self) -> Dict[str, Any]:
        return {"ok": True, "enabled": is_autostart_enabled()}

    def toggle_autostart(self) -> Dict[str, Any]:
        new_val = not is_autostart_enabled()
        res = setup_startup_launcher(new_val)
        return {"ok": res, "enabled": is_autostart_enabled()}

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

    def get_cursor(self) -> Dict[str, Any]:
        """Obtiene la posición global del cursor y la geometría física de la isla para seguimiento 360°."""
        pt = _POINT()
        try:
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        except Exception:
            pass
        win_x, win_y, win_w, win_h = 0, 0, 0, 0
        if self._hwnd:
            try:
                rect = _RECT()
                if ctypes.windll.user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
                    win_x = int(rect.left)
                    win_y = int(rect.top)
                    win_w = int(rect.right - rect.left)
                    win_h = int(rect.bottom - rect.top)
            except Exception:
                pass
        return {
            "cx": int(pt.x),
            "cy": int(pt.y),
            "wx": win_x,
            "wy": win_y,
            "ww": win_w,
            "wh": win_h,
        }

    def get_chat_history(self) -> Dict[str, Any]:
        """Devuelve los mensajes recientes de la conversación activa."""
        msgs = []
        if self._jarvis is not None:
            if hasattr(self._jarvis, "_chat_history") and self._jarvis._chat_history:
                for m in self._jarvis._chat_history[-30:]:
                    msgs.append({"role": m.get("role", "user"), "content": str(m.get("content", ""))[:6000]})
                return {"ok": True, "messages": msgs}

            if hasattr(self._jarvis, "_agent"):
                try:
                    raw = getattr(self._jarvis._agent, "messages", []) or []
                    for m in raw[-30:]:
                        role = m.get("role", "")
                        content = m.get("content", "")
                        if role in ("user", "assistant") and content:
                            msgs.append({"role": role, "content": str(content)[:1200]})
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
    def set_native_handle(self, hwnd: Any, native_form: Any = None) -> None:
        """Registra el HWND real y aplica la geometría y transparencia DWM."""
        try:
            if hasattr(hwnd, "ToInt64"):
                self._hwnd = int(hwnd.ToInt64())
            elif hasattr(hwnd, "ToInt32"):
                self._hwnd = int(hwnd.ToInt32())
            else:
                self._hwnd = int(str(hwnd))
            apply_window_transparency(self._hwnd, native_form)
            self._layout(self._expanded)
            # Asegurar inicio automático en arranque de Windows
            try:
                setup_startup_launcher(True)
            except Exception:
                pass
        except Exception:
            pass

    def _safe_eval_js(self, js_code: str) -> None:
        """Evalúa JavaScript asegurando que se ejecute en el hilo de interfaz (UI thread)."""
        if not self._island_window:
            return
        try:
            native = getattr(self._island_window, "native", None)
            if native is not None and hasattr(native, "InvokeRequired") and native.InvokeRequired:
                import clr
                from System import Action
                native.BeginInvoke(Action(lambda: self._direct_eval(js_code)))
            else:
                self._direct_eval(js_code)
        except Exception:
            pass

    def _direct_eval(self, js_code: str) -> None:
        try:
            self._island_window.evaluate_js(js_code)
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
