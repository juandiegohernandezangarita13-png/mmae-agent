"""
Módulo de Memoria Unificada de MMAE (Macro-Micro Agent Engine).
Proporciona soporte híbrido multicapa:
- ExecutionMemory: Memoria de trabajo y deduplicación a corto plazo.
- UserPersistentMemory: Preferencias y directivas a largo plazo (inspirado en Mem0).
- TemporalKnowledgeGraph: Grafos con validez temporal y resolución de obsolescencia (inspirado en Graffiti).
- HeterogeneousKnowledgeHub: Ingesta heterogénea y RAG documental local (inspirado en Coach).
- BackgroundMemoryWorker: Extracción en segundo plano y adaptación continua (inspirado en LangMem y Leta).
- UnifiedMemorySystem / MMAEMemorySystem: Orquestador integral.
"""
from core.memory.execution import ExecutionMemory
from core.memory.user_memory import UserPersistentMemory, UserMemoryCategory
from core.memory.temporal_graph import TemporalKnowledgeGraph
from core.memory.knowledge_hub import HeterogeneousKnowledgeHub, DocumentChunk
from core.memory.background_worker import BackgroundMemoryWorker
from core.memory.unified_system import UnifiedMemorySystem, MMAEMemorySystem

try:
    from jev.core.memory import HierarchicalMemory
except Exception:
    HierarchicalMemory = None

__all__ = [
    "ExecutionMemory",
    "HierarchicalMemory",
    "UserPersistentMemory",
    "UserMemoryCategory",
    "TemporalKnowledgeGraph",
    "HeterogeneousKnowledgeHub",
    "DocumentChunk",
    "BackgroundMemoryWorker",
    "UnifiedMemorySystem",
    "MMAEMemorySystem"
]
