"""
Módulo de Inferencia Ligera en CPU para MMAE-Agent (core.inference).
"""
from core.inference.cpu_engine import (
    CPUInferenceBackend,
    ClassificationResult,
    HeuristicFastRouter,
    GGUFLocalBackend,
    BitNetBackend,
    LightweightCPUClassifier
)

__all__ = [
    "CPUInferenceBackend",
    "ClassificationResult",
    "HeuristicFastRouter",
    "GGUFLocalBackend",
    "BitNetBackend",
    "LightweightCPUClassifier"
]
