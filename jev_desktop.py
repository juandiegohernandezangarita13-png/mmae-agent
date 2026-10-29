"""
Punto de entrada del JEV de escritorio: isla flotante + ventana completa.

La isla vive siempre encima de las demás ventanas, en el borde superior de la
pantalla. Desde ella se abre la ventana JARVIS completa, se detiene el agente,
se activa la voz o el modo seguro, y se resuelven las aprobaciones.

Ejecución directa:
    .\.venv\Scripts\python.exe jev_desktop.py
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

import webview

from app import JarvisBridge
from jev.config import AgentConfig
from jev.ui.island import (COLLAPSED_SIZE, EXPANDED_SIZE, IslandBridge, compute_position,
                            enable_dpi_awareness, screen_metrics)

BASE = Path(__file__).resolve().parent


def main() -> int:
    enable_dpi_awareness()
    config = AgentConfig()
    bridge = JarvisBridge(config)

    main_html = BASE / "jev" / "ui" / "templates" / "jarvis.html"
    island_html = BASE / "jev" / "ui" / "templates" / "island.html"
    island_bridge = IslandBridge()
    quit_state = {"quitting": False}

    island_width, island_height = COLLAPSED_SIZE
    island_x, island_y = compute_position(island_width)

    # La transparencia depende de WebView2. JEV_ISLAND_OPAQUE=1 fuerza un fondo
    # sólido para diagnosticar o para equipos donde la transparencia falle.
    opaque_island = os.environ.get("JEV_ISLAND_OPAQUE") == "1"

    logical_w, logical_h, _scale = screen_metrics()
    main_width = min(1380, max(960, int(logical_w) - 80))
    main_height = min(860, max(640, int(logical_h) - 120))

    main_window = webview.create_window(
        title="JEV // Autonomous AI",
        url=str(main_html.resolve()),
        js_api=bridge,
        width=main_width,
        height=main_height,
        min_size=(min(1000, main_width), min(650, main_height)),
        background_color="#000000",
        hidden=True,
    )

    island_window = webview.create_window(
        title="JEV Island",
        url=str(island_html.resolve()),
        js_api=island_bridge,
        width=island_width,
        height=island_height,
        x=island_x,
        y=island_y,
        min_size=(200, 60),
        resizable=False,
        frameless=True,
        transparent=not opaque_island,
        on_top=True,
        easy_drag=False,
        focus=False,
        shadow=False,
        background_color="#05070d",
        text_select=False,
    )

    island_bridge.attach(bridge, main_window, island_window, quit_state)

    # La ventana grande se oculta al cerrarla: la isla sigue viva y puede reabrirla.
    def _on_main_closing():
        if quit_state.get("quitting"):
            return True
        try:
            main_window.hide()
        except Exception:
            pass
        return False

    main_window.events.closing += _on_main_closing

    # Ajustes nativos de la isla: sin botón en la barra de tareas.
    def _on_island_loaded():
        try:
            native = getattr(island_window, "native", None)
            if native is not None:
                native.ShowInTaskbar = False
                island_bridge.set_native_handle(int(native.Handle))
        except Exception:
            pass

        if not opaque_island:
            try:
                from System.Drawing import Color

                native = getattr(island_window, "native", None)
                if native is not None:
                    native.BackColor = Color.Transparent
            except Exception:
                pass

        if os.environ.get("JEV_ISLAND_DIAG") == "1":
            info = {}
            try:
                native = getattr(island_window, "native", None)
                info = {
                    "native_type": str(type(native)),
                    "topmost": bool(native.TopMost),
                    "show_in_taskbar": bool(getattr(native, "ShowInTaskbar", None)),
                    "form_border": str(native.FormBorderStyle),
                    "bounds": [int(native.Left), int(native.Top), int(native.Width), int(native.Height)],
                    "back_color": str(native.BackColor),
                    "transparency_key": str(getattr(native, "TransparencyKey", None)),
                    "allow_transparency": bool(getattr(native, "AllowTransparency", False)),
                }
            except Exception as exc:
                info = {"error": repr(exc)}
            try:
                (BASE / "data" / "logs").mkdir(parents=True, exist_ok=True)
                (BASE / "data" / "logs" / "island_diag.json").write_text(
                    json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass

    island_window.events.loaded += _on_island_loaded

    bridge.set_window(main_window)

    def _write_island_state(payload: dict) -> None:
        try:
            (BASE / "data" / "logs").mkdir(parents=True, exist_ok=True)
            (BASE / "data" / "logs" / "island_state.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def _ensure_geometry() -> None:
        """Coloca la isla en píxeles físicos y garantiza que sea visible."""
        user32 = ctypes.windll.user32
        for _ in range(40):
            time.sleep(0.5)
            try:
                native = getattr(island_window, "native", None)
                if native is None:
                    continue
                hwnd = int(native.Handle)
                if not hwnd:
                    continue

                island_bridge.set_native_handle(hwnd)
                time.sleep(5)

                if not user32.IsWindowVisible(hwnd):
                    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                    island_bridge.set_native_handle(hwnd)

                try:
                    from ctypes import wintypes as _wt

                    bounds = _wt.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(bounds))
                    geometry = [int(bounds.left), int(bounds.top),
                                int(bounds.right - bounds.left), int(bounds.bottom - bounds.top)]
                except Exception:
                    geometry = []

                _write_island_state({
                    "ok": True,
                    "hwnd": hwnd,
                    "visible": bool(user32.IsWindowVisible(hwnd)),
                    "geometry_physical": geometry,
                    "screen_physical": [int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))],
                    "dpi": int(user32.GetDpiForWindow(hwnd)),
                    "collapsed": list(COLLAPSED_SIZE),
                    "expanded": list(EXPANDED_SIZE),
                })
                return
            except Exception:
                continue

        # Sin ventana nativa tras 20 s: mostrar la ventana clásica como respaldo.
        _write_island_state({"ok": False, "reason": "island window not created"})
        try:
            main_window.show()
        except Exception:
            pass

    threading.Thread(target=_ensure_geometry, daemon=True).start()

    def _self_test() -> None:
        """Verificación automática opcional (JEV_ISLAND_SELFTEST=1)."""
        if os.environ.get("JEV_ISLAND_SELFTEST") != "1":
            return
        deadline = time.time() + 15
        last_error = ""
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                raw = island_window.evaluate_js(
                    "JSON.stringify({"
                    "api: !!(window.pywebview && window.pywebview.api),"
                    "className: document.body.className,"
                    "state: document.body.getAttribute('data-state'),"
                    "compact: (document.getElementById('compactState') || {}).textContent,"
                    "activity: (document.getElementById('activityText') || {}).textContent"
                    "})"
                )
                if raw:
                    print("ISLAND_SELFTEST=" + str(raw), flush=True)
                    break
            except Exception as exc:  # pragma: no cover - depende de la GUI
                last_error = str(exc)
        else:
            print("ISLAND_SELFTEST_FAILED=" + last_error, flush=True)
        try:
            island_bridge.quit_app()
        except Exception:
            pass

    webview.start(_self_test, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
