"""
Núcleo del Agente Autónomo Unificado MMAE (Macro-Micro Agent Engine).
Integra la inferencia de dos fases (Macro-Estructura y Micro-Relleno) con
el bucle cognitivo ReAct, validación de sintaxis, canal determinista y suite de herramientas.
"""
import sys
from typing import Dict, Any, Optional

from config import config, AgentConfig
from utils.logger import log
from utils.env_manager import EnvironmentManager
from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine
from core.memory import ExecutionMemory, HierarchicalMemory
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

        # Conectar herramientas del núcleo avanzado si existen
        if self.agent_core and hasattr(self.agent_core, "registry"):
            for tool_name in self.agent_core.registry.list_tools():
                tool_inst = self.agent_core.registry.get(tool_name)
                if tool_inst and tool_name not in self.registry.skills:
                    self.registry.register(tool_name, tool_inst.description)(tool_inst.execute)

    def run(self, user_goal: str) -> Dict[str, Any]:
        """
        Ejecuta un objetivo completo utilizando la arquitectura Macro-Micro (MMAE).
        """
        log.info(f"🎯 [Objetivo General]: {user_goal}")

        # Fase 1: Esqueleto Macro y Desglose en Tareas
        log.info("📋 Generando esqueleto macro...")
        macro_output = self.macro.generate_skeleton(user_goal)
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
        log.info("🏁 Objetivo completado. Estado persistido con éxito.")
        return {
            "goal": user_goal,
            "skeleton": macro_output.get("skeleton"),
            "tasks": tasks,
            "results": results
        }


__all__ = ["MMAEAutonomousAgent", "AgentCore"]
