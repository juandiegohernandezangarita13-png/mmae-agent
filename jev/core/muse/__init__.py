"""
Módulo Muse Spark para JEV.
Arquitectura cognitiva de bucle autónomo con canal de intención previo,
planificación persistente en SQLite y ejecución desacoplada de herramientas.
"""
from jev.core.muse.tool_registry import ToolRegistry, ToolDefinition
from jev.core.muse.execution_engine import ExecutionEngine, ExecutionResult
from jev.core.muse.state_manager import (
    MuseStateManager,
    PlanStep,
    StepStatus,
    TaskStatus,
    TurnRecord
)
from jev.core.muse.agent_loop import AgentLoop, LoopResult
from jev.core.muse.prompts import MUSE_SPARK_SYSTEM_PROMPT, PLANNING_SYSTEM_PROMPT

__all__ = [
    "AgentLoop",
    "LoopResult",
    "ToolRegistry",
    "ToolDefinition",
    "ExecutionEngine",
    "ExecutionResult",
    "MuseStateManager",
    "PlanStep",
    "StepStatus",
    "TaskStatus",
    "TurnRecord",
    "MUSE_SPARK_SYSTEM_PROMPT",
    "PLANNING_SYSTEM_PROMPT"
]
