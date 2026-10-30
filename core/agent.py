"""
Núcleo del Agente Autónomo Unificado MMAE (Macro-Micro Agent Engine).
Integra la inferencia de dos fases (Macro-Estructura y Micro-Relleno) con
el bucle cognitivo ReAct, validación de sintaxis, canal determinista y suite de herramientas.
"""
import sys
import os
from typing import Dict, Any, Optional

from config import config, AgentConfig
from utils.logger import log
from utils.env_manager import EnvironmentManager
from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine
from core.memory import (
    ExecutionMemory,
    HierarchicalMemory,
    UnifiedMemorySystem,
    UserPersistentMemory,
    TemporalKnowledgeGraph,
    HeterogeneousKnowledgeHub,
    MMAEMemorySystem
)
from core.reflection_loop import ReflectionLoop
from core.planner import TaskPlanner
from core.persistence import StatePersistence
from core.evaluator import OutputEvaluator
from core.executor import AgentExecutor

from skills.base import SkillRegistry
from skills.terminal import SafeTerminalSkill
from skills.filesystem import SafeFileSystemSkill
from skills.web import SafeWebSkill
from skills.git_ops import GitOperationsSkill
from skills.system_monitor import SystemMonitorSkill

try:
    from jev.core.agent import AgentCore
except Exception:
    AgentCore = None

from jev_router import JevRouter, PreFlightDecision, ChoiceResult, ScoreResult, NoulResult


class MMAEAutonomousAgent:
    """
    Orquestador unificado del Agente Autónomo MMAE.
    Combina la arquitectura Macro-Micro (Fase 1 y Fase 2 con LiteralBypass)
    con las capacidades avanzadas de JEV (Multimodal, Claude Code, FastPath, Memoria Jerárquica).
    """
    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self.config = agent_config or config
        log.info("Inicializando MMAE Autonomous Agent...")
        
        # 1. Persistencia y Estado
        self.persistence = StatePersistence()
        self.state = self.persistence.load_state()
        
        # 2. Memoria y Reflexión
        self.memory = ExecutionMemory(max_history=self.config.max_history_turns)
        self.hierarchical_memory = HierarchicalMemory() if HierarchicalMemory else None
        
        # Sistema de Memoria Avanzada Unificada (Mem0 + Graffiti + Coach + LangMem + Leta)
        self.unified_memory = UnifiedMemorySystem(
            memory_dir=getattr(self.config, "memory_dir", None),
            execution_memory=self.memory,
            hierarchical_memory=self.hierarchical_memory,
            auto_start_worker=False
        )
        
        self.reflection = ReflectionLoop(memory=self.memory, max_retries=self.config.max_retries_per_step)
        self.planner = TaskPlanner()
        self.evaluator = OutputEvaluator()

        # 3. Núcleo Cognitivo Avanzado y Registro de Skills
        self.agent_core = AgentCore(config=self.config) if AgentCore else None
        self.registry = SkillRegistry()
        self._register_skills()

        # 4. Motores de Inferencia (Macro / Micro) y Ejecutor
        self.macro = MacroEngine(api_base_url=self.config.api_base_url)
        self.micro = MicroEngine(api_base_url=self.config.api_base_url)
        self.executor = AgentExecutor(registry=self.registry)

        # 5. Enrutador System-1 Jev (TypeSafe AI) para decisiones sub-200ms
        self.jev_router = JevRouter(
            api_key=getattr(self.config, "typesafe_api_key", os.getenv("TYPESAFE_API_KEY", "")),
            api_url=getattr(self.config, "typesafe_api_url", os.getenv("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")),
            timeout_seconds=getattr(self.config, "typesafe_timeout_seconds", 0.200)
        )
        
        log.info("MMAE inicializado y listo para operar.")

    def _register_skills(self):
        # Terminal segura
        terminal = SafeTerminalSkill(default_timeout=self.config.terminal_timeout_seconds)
        self.registry.register("run_terminal", "Ejecuta un comando en terminal.")(terminal.run)
        
        # Sistema de archivos
        fs = SafeFileSystemSkill(base_directory=self.config.safe_working_directory)
        self.registry.register("read_file", "Lee el contenido de un archivo.")(fs.read_file)
        self.registry.register("write_file", "Escribe contenido en un archivo.")(fs.write_file)

        # Web
        web = SafeWebSkill()
        self.registry.register("fetch_url", "Consulta contenido vía HTTP.")(web.fetch_url)

        # Git
        git = GitOperationsSkill(repo_path=self.config.safe_working_directory)
        self.registry.register("git_status", "Revisa el estado del repositorio git.")(git.status)
        self.registry.register("git_diff", "Muestra diferencias de código en git.")(git.diff)
        self.registry.register("git_commit", "Guarda cambios en un commit.")(git.commit_changes)

        # Monitor de sistema
        sys_monitor = SystemMonitorSkill()
        self.registry.register("system_stats", "Obtiene métricas de CPU, disco y SO.")(sys_monitor.get_system_stats)

        # Habilidades de Memoria Persistente Avanzada (Mem0 + Graffiti + Coach)
        self.registry.register(
            "memory_search_user",
            "Busca en las preferencias y hechos persistentes del usuario (Mem0)."
        )(lambda query, category=None: self.unified_memory.user.search(query=query, category=category))

        self.registry.register(
            "memory_add_preference",
            "Añade o actualiza una preferencia o directiva de usuario (Mem0)."
        )(lambda key, value, category="preference": self.unified_memory.user.add(key=key, value=value, category=category))

        self.registry.register(
            "memory_temporal_query",
            "Consulta hechos temporales vigentes o históricos en el grafo de conocimiento (Graffiti)."
        )(lambda source="User", relation=None: self.unified_memory.temporal.get_current_facts(source=source, relation=relation))

        self.registry.register(
            "knowledge_search_docs",
            "Busca información relevante en documentos locales ingestados y fuentes externas (Coach Hub)."
        )(lambda query, top_k=3: self.unified_memory.knowledge.query(query_text=query, top_k=top_k))

        self.registry.register(
            "knowledge_ingest_file",
            "Ingesta e indexa un archivo local (PDF, Markdown, TXT, código) en el Knowledge Hub (Coach)."
        )(lambda file_path: {"chunks_indexed": self.unified_memory.knowledge.ingest_file(file_path)})

        # Conectar herramientas del núcleo avanzado si existen
        if self.agent_core and hasattr(self.agent_core, "registry"):
            for tool_name in self.agent_core.registry.list_tools():
                tool_inst = self.agent_core.registry.get(tool_name)
                if tool_inst and tool_name not in self.registry.skills:
                    self.registry.register(tool_name, tool_inst.description)(tool_inst.execute)

    def run(self, user_goal: str) -> Dict[str, Any]:
        """
        Ejecuta un objetivo completo utilizando la arquitectura Macro-Micro (MMAE),
        optimizada con el enrutador System-1 Jev de TypeSafe AI (<200ms).
        """
        log.info(f"🎯 [Objetivo General]: {user_goal}")

        # Pre-Flight System-1 Jev Router (<200ms)
        preflight: PreFlightDecision = self.jev_router.pre_flight_check(user_goal)
        log.info(
            f"⚡ [Jev System-1 Router ({preflight.total_latency_ms:.1f}ms)]: "
            f"Ruta={preflight.action} | Seguridad={preflight.safety.allowed} | Complejidad={preflight.complexity.score:.2f}"
        )

        # Si Noul detecta un riesgo inminente, abortar antes de gastar tokens de inferencia pesada
        if preflight.action == "blocked_security":
            reason = preflight.direct_response or "Acción bloqueada por seguridad System-1 (Jev Noul)"
            log.warning(f"🚨 [Noul Bloqueo]: {reason}")
            return {
                "goal": user_goal,
                "error": reason,
                "success": False,
                "results": [{"task": "Pre-flight Noul Check", "result": {"success": False, "error": reason}}]
            }

        # Recuperación de Memoria Unificada (Mem0 + Graffiti + Coach + Leta)
        memory_context = self.unified_memory.build_unified_context(query=user_goal)
        if memory_context:
            log.info(f"🧠 [Memoria Unificada]: Contexto activo recuperado ({len(memory_context)} caracteres).")

        # Fase 1: Esqueleto Macro y Desglose en Tareas
        log.info("📋 Generando esqueleto macro...")
        macro_prompt = f"{user_goal}\n\n{memory_context}" if memory_context else user_goal
        macro_output = self.macro.generate_skeleton(macro_prompt)
        tasks = self.planner.parse_tasks_from_skeleton(macro_output["skeleton"])

        results = []

        # Fase 2: Ejecución secuencial y guiada de cada subtarea
        while not self.planner.is_finished():
            current_task = self.planner.get_next_task()
            if not current_task:
                break

            task_desc = current_task["description"]
            log.info(f"\n▶️ Ejecutando Tarea [{current_task['id']}]: {task_desc}")

            def step_execution():
                # Expansión micro con bypass activo
                micro_input = {
                    "skeleton": f"Objetivo: {user_goal}\nTarea actual: {task_desc}",
                    "literals": macro_output.get("literals", [])
                }
                detailed_step = self.micro.expand_skeleton(micro_input)

                # Filtro de seguridad binario Noul (<10ms) sobre la acción antes de ejecutar
                step_repr = str(detailed_step)
                noul_eval = self.jev_router.noul(step_repr, check_type="action_safety")
                if not noul_eval.allowed:
                    err_msg = noul_eval.violation_reason or "Acción bloqueada por seguridad Noul"
                    log.warning(f"🚨 [Noul Bloqueo en Tarea]: {err_msg}")
                    return {
                        "success": False,
                        "error": f"⛔ ACCIÓN CANCELADA: {err_msg}",
                        "output": ""
                    }
                
                # Ejecutar acción si existe llamada a herramienta
                execution_result = self.executor.process_and_execute(detailed_step)
                return execution_result

            # Ejecución con ciclo de reflexión y reintentos
            result = self.reflection.execute_with_retry(task_desc, step_execution)
            self.planner.complete_current_task(success=result.get("success", False))
            results.append({"task": task_desc, "result": result})

        # Guardar estado acumulado en disco
        self.persistence.save_state({
            "history": self.memory.history,
            "env_snapshot": EnvironmentManager.snapshot()
        })

        # Destilación y aprendizaje adaptativo continuo (LangMem + Leta)
        tools_used = [r.get("task", "") for r in results]
        overall_success = all(r.get("result", {}).get("success", False) for r in results) if results else True
        self.unified_memory.record_turn_and_learn(
            user_input=user_goal,
            agent_output=str(results),
            tools_used=tools_used,
            task_success=overall_success,
            sync=True
        )

        log.info("🏁 Objetivo completado. Estado persistido con éxito.")
        return {
            "goal": user_goal,
            "skeleton": macro_output.get("skeleton"),
            "tasks": tasks,
            "results": results
        }


__all__ = ["MMAEAutonomousAgent", "AgentCore"]
