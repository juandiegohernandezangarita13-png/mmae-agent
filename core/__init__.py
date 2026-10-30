"""
Paquete core del Agente Autónomo MMAE.
"""
from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine
from core.planner import TaskPlanner
from core.memory import (
    ExecutionMemory,
    HierarchicalMemory,
    UnifiedMemorySystem,
    UserPersistentMemory,
    TemporalKnowledgeGraph,
    HeterogeneousKnowledgeHub,
    BackgroundMemoryWorker,
    MMAEMemorySystem
)
from core.reflection_loop import ReflectionLoop
from core.persistence import StatePersistence
from core.evaluator import OutputEvaluator
from core.executor import AgentExecutor
from core.agent import MMAEAutonomousAgent, AgentCore
from core.fast_path import FastPathRouter, FastPathResult

__all__ = [
    "MacroEngine",
    "MicroEngine",
    "TaskPlanner",
    "ExecutionMemory",
    "HierarchicalMemory",
    "UnifiedMemorySystem",
    "UserPersistentMemory",
    "TemporalKnowledgeGraph",
    "HeterogeneousKnowledgeHub",
    "BackgroundMemoryWorker",
    "MMAEMemorySystem",
    "ReflectionLoop",
    "StatePersistence",
    "OutputEvaluator",
    "AgentExecutor",
    "MMAEAutonomousAgent",
    "AgentCore",
    "FastPathRouter",
    "FastPathResult"
]
