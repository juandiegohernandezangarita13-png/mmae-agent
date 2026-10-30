"""
Sistema de Memoria Unificada Avanzada para MMAE-Agent.
Orquesta y unifica las 5 dimensiones de memoria:
1. Mem0: Capa de preferencias y hechos de usuario a largo plazo con resolución de conflictos.
2. Graffiti: Grafo de conocimiento temporal con control de validez e invalidación automática.
3. Coach: Ingesta heterogénea y RAG local sobre archivos, PDFs, Markdown y web.
4. LangMem & Leta: Extractor en segundo plano no bloqueante y evolución adaptativa del perfil.
5. ExecutionMemory: Control de bucles y pasos a corto plazo en sesión activa.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from core.memory.execution import ExecutionMemory
from core.memory.user_memory import UserPersistentMemory, UserMemoryCategory
from core.memory.temporal_graph import TemporalKnowledgeGraph
from core.memory.knowledge_hub import HeterogeneousKnowledgeHub
from core.memory.background_worker import BackgroundMemoryWorker

try:
    from jev.core.memory import HierarchicalMemory
except Exception:
    HierarchicalMemory = None


class UnifiedMemorySystem:
    """
    Sistema unificado de memoria cognitiva para el agente autónomo MMAE.
    Combina persistencia de usuario, razonamiento temporal, RAG documental local,
    aprendizaje asíncrono y prevención de bucles.
    """

    def __init__(
        self,
        memory_dir: Optional[Union[str, Path]] = None,
        execution_memory: Optional[ExecutionMemory] = None,
        hierarchical_memory: Optional[Any] = None,
        auto_start_worker: bool = False
    ):
        self.memory_dir = Path(memory_dir or "data/memory").resolve()
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 1. Memoria de Ejecución de Corto Plazo
        self.execution = execution_memory or ExecutionMemory()

        # 2. Capa Persistente de Usuario (Mem0)
        self.user = UserPersistentMemory(db_path=self.memory_dir / "user_memory.db")

        # 3. Grafo de Conocimiento Temporal (Graffiti)
        self.temporal = TemporalKnowledgeGraph(db_path=self.memory_dir / "temporal_graph.db")

        # 4. Hub de Conocimiento Heterogéneo y RAG Local (Coach)
        self.knowledge = HeterogeneousKnowledgeHub(storage_dir=self.memory_dir / "knowledge_hub")

        # 5. Motor de Aprendizaje en Segundo Plano y Adaptación (LangMem + Leta)
        self.background = BackgroundMemoryWorker(
            user_memory=self.user,
            temporal_graph=self.temporal,
            profile_path=self.memory_dir / "adaptive_profile.json"
        )

        # 6. Memoria Procedimental Jerárquica Existente (JEV SQLite)
        if hierarchical_memory is not None:
            self.hierarchical = hierarchical_memory
        elif HierarchicalMemory is not None:
            self.hierarchical = HierarchicalMemory(memory_dir=self.memory_dir)
        else:
            self.hierarchical = None

        if auto_start_worker:
            self.background.start()

    def build_unified_context(
        self,
        query: str,
        user_id: str = "default_user",
        include_execution: bool = True,
        top_k_docs: int = 2
    ) -> str:
        """
        Sintetiza de forma compacta y estructurada todas las capas de memoria
        para inyección directa en el prompt del sistema del agente sin saturar tokens.
        """
        sections: List[str] = []

        # 1. Perfil y Preferencias de Usuario (Mem0)
        user_ctx = self.user.get_user_profile_context(user_id=user_id)
        if user_ctx:
            sections.append(user_ctx)

        # 2. Grafo Temporal (Graffiti)
        temp_ctx = self.temporal.get_temporal_context_summary(focus_source="User")
        if temp_ctx:
            sections.append(temp_ctx)

        # 3. RAG Documental Local (Coach)
        if query:
            doc_ctx = self.knowledge.format_retrieval_context(query_text=query, top_k=top_k_docs)
            if doc_ctx:
                sections.append(doc_ctx)

        # 4. Soluciones Procedimentales Previas (JEV Memory)
        if self.hierarchical and query:
            try:
                proc_ctx = self.hierarchical.get_procedural_context_for_goal(query)
                if proc_ctx and "SOLUCIÓN PROCEDIMENTAL PREVIA" in proc_ctx:
                    sections.append(proc_ctx)
            except Exception:
                pass

        # 5. Perfil Adaptativo (Leta)
        leta_ctx = self.background.get_adaptive_context_summary()
        if leta_ctx:
            sections.append(leta_ctx)

        # 6. Historial de Pasos Recientes (ExecutionMemory)
        if include_execution:
            exec_ctx = self.execution.get_context_summary()
            if exec_ctx and exec_ctx != "Sin acciones previas registradas.":
                sections.append(f"[HISTORIAL DE EJECUCIÓN RECIENTE]:\n{exec_ctx}")

        return "\n\n".join(sections)

    def record_turn_and_learn(
        self,
        user_input: str,
        agent_output: str,
        tools_used: Optional[List[str]] = None,
        task_success: bool = True,
        user_id: str = "default_user",
        sync: bool = False
    ) -> None:
        """
        Registra el turno completado y activa el aprendizaje en segundo plano (LangMem / Leta).
        Si sync=True, procesa de inmediato en el mismo hilo.
        """
        self.background.enqueue_turn(
            user_input=user_input,
            agent_output=agent_output,
            tools_used=tools_used,
            task_success=task_success,
            user_id=user_id
        )
        if sync:
            self.background.process_pending(sync=True)

    def close(self) -> None:
        """Detiene de forma segura los hilos de fondo."""
        if self.background.is_running():
            self.background.stop()


# Alias de compatibilidad
MMAEMemorySystem = UnifiedMemorySystem
