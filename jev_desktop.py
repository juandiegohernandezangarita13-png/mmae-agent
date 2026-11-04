"""
Punto de entrada del Pato de Escritorio (Desktop Duck Companion) de MMAE.
Compañero interactivo animado en pixel-art que camina sobre la barra de tareas de Windows,
100% transparente (sin recuadro blanco), animando físicamente los pies a cada paso
y abriendo la interfaz al tocarlo dos veces.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Autodescubrimiento del entorno virtual local para máxima portabilidad
_base_dir = Path(__file__).resolve().parent
_venv_site = _base_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.append(str(_venv_site))
if str(_base_dir) not in sys.path:
    sys.path.insert(0, str(_base_dir))

from config import AgentConfig
from jev.ui.duck_pet import run_duck


def main() -> int:
    config = AgentConfig()
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
            print(f"[WARN] No se pudo inicializar CuriosityDaemon: {e}")

    try:
        return run_duck()
    finally:
        if curiosity_daemon:
            curiosity_daemon.stop()


if __name__ == "__main__":
    sys.exit(main())
