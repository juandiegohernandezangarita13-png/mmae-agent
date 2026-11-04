"""
Módulo de Harness Recursivo (Harness² Architecture para MMAE / JEV).
Inspirado en Harness² (Google Research, 2026: arXiv:2610.14224).

Provee:
1. Árbol de Harness Mutable (c1..c8: prompts, guardrails, memory, skills, tools, scripts, subagents, plugins).
2. Biblioteca de Experiencias Persistente (R) con tuplas transferibles (cue, lesson, evidence).
3. Ciclo de Recursión Propose-Probe-Compose a nivel de tarea.
4. Salvaguardas de frontera de evidencia (Evidence Boundary y Answer-Free).
"""
from core.harness.tree import HarnessTree, HarnessComponent
from core.harness.library import ExperienceLibrary
from core.harness.recursion import RecursiveHarnessImprover

__all__ = [
    "HarnessTree",
    "HarnessComponent",
    "ExperienceLibrary",
    "RecursiveHarnessImprover",
]
