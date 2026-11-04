"""
Punto de entrada del Pato de Escritorio (Desktop Duck Companion) de MMAE.
Compañero interactivo animado en pixel-art que camina sobre la barra de tareas de Windows,
muestra el estado de actividad del agente en tiempo real y permite ingresar a la interfaz
completa tocándolo dos veces (doble clic).
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

# Autodescubrimiento del entorno virtual local para máxima portabilidad
_base_dir = Path(__file__).resolve().parent
_venv_site = _base_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.append(str(_venv_site))
if str(_base_dir) not in sys.path:
    sys.path.insert(0, str(_base_dir))

import webview

from app import JarvisBridge
from jev.config import AgentConfig
from jev.ui.duck_companion import (
    DuckBridge,
    compute_duck_position,
    enable_dpi_awareness,
    screen_metrics,
)

BASE = Path(__file__).resolve().parent


def main() -> int:
    # Mutex de instancia única en Windows para evitar duplicados en pantalla
    _single_instance_mutex = None
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            _single_instance_mutex = kernel32.CreateMutexW(None, True, "Local\\MMAE_DesktopDuck_SingleInstance")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                print("[INFO] El Pato de Escritorio MMAE ya está activo.")
                return 0
        except Exception:
            pass

    enable_dpi_awareness()
    config = AgentConfig()
    bridge = JarvisBridge(config)

    duck_html = BASE / "jev" / "ui" / "templates" / "duck.html"
    duck_bridge = DuckBridge()

    # Tamaño del widget: 280x200 px (el pato mide ~128px de alto = ~3.4 cm en pantalla)
    duck_width = 280
    duck_height = 200
    duck_x, duck_y = compute_duck_position(duck_width, duck_height)

    duck_window = webview.create_window(
        title="MMAE Desktop Duck",
        url=str(duck_html.resolve()),
        js_api=duck_bridge,
        width=duck_width,
        height=duck_height,
        x=duck_x,
        y=duck_y,
        min_size=(240, 160),
        resizable=False,
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=True,
        focus=False,
        shadow=False,
        background_color="#000000",
        text_select=False,
    )

    duck_bridge.attach(duck_window, bridge)

    # Iniciar demonio de curiosidad en segundo plano si está habilitado
    curiosity_daemon = None
    if getattr(config, "curiosity_enabled", True):
        try:
            from core.curiosity_daemon import CuriosityDaemon
            from core.voice_announcer import VoiceAnnouncer
            voice_announcer = VoiceAnnouncer(enabled=getattr(config, "voice_enabled", True))
            curiosity_daemon = CuriosityDaemon(
                idle_threshold_seconds=getattr(config, "curiosity_idle_seconds", 900.0),
                voice_announcer=voice_announcer,
            )
            curiosity_daemon.start()
        except Exception as e:
            print(f"[WARN] No se pudo inicializar CuriosityDaemon en el pato: {e}")

    def _on_started() -> None:
        """Configura transparencia total a nivel HWND nativo para eliminar bordes blancos."""
        try:
            native = getattr(duck_window, "native", None)
            if native is not None:
                try:
                    native.ShowInTaskbar = False
                except Exception:
                    pass

                handle = getattr(native, "Handle", None)
                if handle is not None:
                    hwnd = int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(str(handle))
                    duck_bridge.set_native_handle(hwnd, native)
        except Exception:
            pass

    try:
        webview.start(_on_started, debug=False)
    finally:
        if curiosity_daemon:
            curiosity_daemon.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
