"""
Núcleo del Agente JEV.
Módulos de autorreflexión y autoevolución en tiempo de ejecución.
"""
from jev.core.self_evolving_agent import (
    SelfEvolvingAgent,
    ReflectionCognitiveLoop,
    CodeSynthesizer,
    HotReloadingInjector,
    TaskStatePreserver,
    ToolSpecification,
    SuspendedTaskState
)
from jev.core.muse import (
    AgentLoop,
    ToolRegistry,
    ToolDefinition,
    ExecutionEngine,
    ExecutionResult,
    MuseStateManager,
    PlanStep,
    StepStatus,
    TaskStatus,
    LoopResult,
    MUSE_SPARK_SYSTEM_PROMPT
)
