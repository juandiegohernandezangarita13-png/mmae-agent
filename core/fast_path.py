"""
Re-exportación de compatibilidad directa para Fast Path Router.
Permite importación como `from core.fast_path import FastPathRouter` o `jev.core.fast_path`.
"""
from jev.core.fast_path import (
    FastPathRouter,
    FastPathResult,
    ContactManager,
    WhatsAppDispatcher,
    normalize_accents
)

__all__ = [
    "FastPathRouter",
    "FastPathResult",
    "ContactManager",
    "WhatsAppDispatcher",
    "normalize_accents"
]
