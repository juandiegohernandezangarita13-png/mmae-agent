"""
Puente y módulo de persistencia de memoria para MMAE.
Proporciona acceso directo a ProceduralMemoryManager y funciones de decaimiento temporal.
"""
from core.memory.procedure_store import (
    ProceduralMemoryManager,
    ProceduralRecord,
    DEFAULT_DB_PATH,
)

__all__ = [
    "ProceduralMemoryManager",
    "ProceduralRecord",
    "DEFAULT_DB_PATH",
]
