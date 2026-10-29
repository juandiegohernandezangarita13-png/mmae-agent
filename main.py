import sys
from config import config
from utils.logger import log
from utils.env_manager import EnvironmentManager
from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine
from core.memory import ExecutionMemory
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

class MMAEAutonomousAgent:
    """
    Orquestador integral del agente autónomo bajo la arquitectura Macro-Micro (MMAE).
    """
    def __init__(self):
        log.info("Inicializando MMAE Autonomous Agent...")
        
        # 1. Configuración y persistencia
        self.persistence = StatePersistence()
        self.state = self.persistence.load_state()
        
        # 2. Memoria y reflexión
        self.memory = ExecutionMemory(max_history=config.max_history_turns)
        self.reflection = ReflectionLoop(memory=self.memory, max_retries=config.max_retries_per_step)
        self.planner = TaskPlanner()
        self.evaluator = OutputEvaluator()

        # 3. Registro y vinculación de Skills
        self.registry = SkillRegistry()
        self._register_skills()

        # 4. Motores de Inferencia (Macro / Micro) y Ejecutor
        self.macro = MacroEngine(api_base_url=config.api_base_url)
        self.micro = MicroEngine(api_base_url=config.api_base_url)
        self.executor = AgentExecutor(registry=self.registry)
        
        log.info("MMAE inicializado y listo para recibir objetivos.")

    def _register_skills(self):
        # Terminal
        terminal = SafeTerminalSkill(default_timeout=config.terminal_timeout_seconds)
        self.registry.register("run_terminal", "Ejecuta un comando en terminal.")(terminal.run)
        
        # Filesystem
        fs = SafeFileSystemSkill(base_directory=config.safe_working_directory)
        self.registry.register("read_file", "Lee el contenido de un archivo.")(fs.read_file)
        self.registry.register("write_file", "Escribe contenido en un archivo.")(fs.write_file)

        # Web
        web = SafeWebSkill()
        self.registry.register("fetch_url", "Consulta contenido vía HTTP.")(web.fetch_url)

        # Git
        git = GitOperationsSkill(repo_path=config.safe_working_directory)
        self.registry.register("git_status", "Revisa el estado del repositorio git.")(git.status)
        self.registry.register("git_diff", "Muestra diferencias de código en git.")(git.diff)
        self.registry.register("git_commit", "Guarda cambios en un commit.")(git.commit_changes)

        # Monitor de sistema
        sys_monitor = SystemMonitorSkill()
        self.registry.register("system_stats", "Obtiene métricas de CPU, disco y SO.")(sys_monitor.get_system_stats)

    def run(self, user_goal: str):
        log.info(f"🎯 [Objetivo General]: {user_goal}")

        # Fase 1: Esqueleto Macro y Desglose en Tareas
        log.info("📋 Generando esqueleto macro...")
        macro_output = self.macro.generate_skeleton(user_goal)
        tasks = self.planner.parse_tasks_from_skeleton(macro_output["skeleton"])

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
                    "literals": macro_output["literals"]
                }
                detailed_step = self.micro.expand_skeleton(micro_input)
                
                # Ejecutar acción si existe llamada a herramienta
                execution_result = self.executor.process_and_execute(detailed_step)
                return execution_result

            # Ejecución con ciclo de reflexión y reintentos
            result = self.reflection.execute_with_retry(task_desc, step_execution)
            self.planner.complete_current_task(success=result.get("success", False))

        # Guardar estado acumulado en disco
        self.persistence.save_state({
            "history": self.memory.history,
            "env_snapshot": EnvironmentManager.snapshot()
        })
        log.info("🏁 Objetivo completado. Estado persistido con éxito.")

if __name__ == "__main__":
    agent = MMAEAutonomousAgent()
    goal = "Auditar el espacio en disco, listar los archivos locales y reportar el estado."
    agent.run(goal)
