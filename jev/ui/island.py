"""
Módulo de compatibilidad y alias: Redirige hacia Duck Companion.
Preserva las firmas y funciones de utilidad (screen_metrics, enable_dpi_awareness)
para evitar roturas en el resto del proyecto tras la remoción del widget de la píldora.
"""
from __future__ import annotations

from jev.ui.duck_companion import (
    DuckBridge,
    enable_dpi_awareness,
    screen_metrics,
    compute_duck_position,
    apply_duck_transparency,
)

# Dimensiones compatibles
COLLAPSED_SIZE = (280, 200)
EXPANDED_SIZE = (280, 200)
WIDGET_SIZE = (280, 200)

# Alias de compatibilidad
IslandBridge = DuckBridge
compute_position = compute_duck_position
apply_window_transparency = apply_duck_transparency

__all__ = [
    "IslandBridge",
    "DuckBridge",
    "COLLAPSED_SIZE",
    "EXPANDED_SIZE",
    "WIDGET_SIZE",
    "enable_dpi_awareness",
    "screen_metrics",
    "compute_position",
    "compute_duck_position",
    "apply_window_transparency",
    "apply_duck_transparency",
]
