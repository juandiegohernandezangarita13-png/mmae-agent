"""
Módulo de Razonamiento Profundo (Deep Reasoning Engine) y Verificación Empírica.
Proporciona deliberación multi-hipótesis antes de actuar, verificación empírica
de resultados en disco/red y auto-diagnóstico causal de fallos.
"""
from .deep_thinker import DeepThinker, ReasoningHypothesis, VerificationResult

__all__ = ["DeepThinker", "ReasoningHypothesis", "VerificationResult"]
