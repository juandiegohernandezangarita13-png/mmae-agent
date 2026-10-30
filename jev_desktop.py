"""
Punto de entrada de la Isla de escritorio de MMAE (Macro-Micro Autonomous Agent Engine).
Compañero flotante en el borde superior de la pantalla, estilo Coucou / Dynamic Island.

Ejecución directa:
    .\\.venv\\Scripts\\python.exe main.py --desktop
    .\\iniciar.bat
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import webview

from app import JarvisBridge
from jev.config import AgentConfig
from jev.ui.island import (COLLAPSED_SIZE, EXPANDED_SIZE, IslandBridge, compute_position,
                            enable_dpi_awareness, screen_metrics)

BASE = Path(__file__).resolve().parent


def main() -> int:
    # Mutex de instancia única en Windows para evitar duplicados en pantalla
    _single_instance_mutex = None
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            _single_instance_mutex = kernel32.CreateMutexW(None, True, "Local\\MMAE_JEV_Island_SingleInstance")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                print("[INFO] La Isla flotante MMAE ya está abierta en otra ventana.")
                return 0
        except Exception:
            pass

    enable_dpi_awareness()
    config = AgentConfig()
    bridge = JarvisBridge(config)

    island_html = BASE / "jev" / "ui" / "templates" / "island.html"
    island_bridge = IslandBridge()
    quit_state = {"quitting": False}

    island_width, island_height = COLLAPSED_SIZE
    island_x, island_y = compute_position(island_width)

    opaque_island = os.environ.get("JEV_ISLAND_OPAQUE") == "1"

    island_window = webview.create_window(
        title="MMAE Island",
        url=str(island_html.resolve()),
        js_api=island_bridge,
        width=island_width,
        height=island_height,
        x=island_x,
        y=island_y,
        min_size=(200, 50),
        resizable=False,
        frameless=True,
        transparent=not opaque_island,
        on_top=True,
        easy_drag=False,
        focus=True,
        shadow=False,
        background_color="#000000",
        text_select=True,
    )

    island_bridge.attach(bridge, None, island_window, quit_state)

    def _on_started() -> None:
        """Configura el HWND nativo tras el renderizado de la ventana."""
        try:
            native = getattr(island_window, "native", None)
            if native is not None:
                try:
                    native.ShowInTaskbar = False
                except Exception:
                    pass

                # Auto-reducir la isla cuando el usuario interactúe con otra app (Deactivate)
                try:
                    def _on_deactivate(sender, args):
                        if getattr(island_bridge, "_expanded", False):
                            island_bridge.collapse()
                    native.Deactivate += _on_deactivate
                except Exception:
                    pass

                handle = getattr(native, "Handle", None)
                if handle is not None:
                    hwnd = int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(str(handle))
                    island_bridge.set_native_handle(hwnd, native)
        except Exception:
            pass

    webview.start(_on_started, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
