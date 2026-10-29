"""
Planificador y Descompositor de Tareas (DAG Planner) para JEV.
Divide metas complejas en un Grafo Acíclico Dirigido (DAG) de micro-tareas secuenciales,
con criterios objetivos de verificación y límite estricto de 3 reintentos por subtarea antes de pivotar.
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import json

from jev.core.llm_client import LocalLLMClient


@dataclass
class SubTask:
    """Representa una micro-tarea dentro del plan DAG."""
    id: int
    title: str
    description: str
    expected_verification: str
    status: str = "pending"  # 'pending', 'in_progress', 'completed', 'failed', 'pivoted'
    retries: int = 0
    max_retries: int = 3
    dependencies: List[int] = field(default_factory=list)
    output_summary: Optional[str] = None

    def can_start(self, completed_ids: List[int]) -> bool:
        return all(dep in completed_ids for dep in self.dependencies)


class TaskPlan:
    """Gestiona el estado y progresión del grafo de micro-tareas."""

    def __init__(self, goal: str, tasks: List[SubTask]):
        self.goal = goal
        self.tasks = tasks

    def get_next_available_task(self) -> Optional[SubTask]:
        completed = [t.id for t in self.tasks if t.status == "completed"]
        for t in self.tasks:
            if t.status in ["pending", "in_progress"] and t.can_start(completed):
                t.status = "in_progress"
                return t
        return None

    def mark_completed(self, task_id: int, output_summary: Optional[str] = None):
        for t in self.tasks:
            if t.id == task_id:
                t.status = "completed"
                if output_summary:
                    t.output_summary = output_summary

    def record_failure_and_check_pivot(self, task_id: int, reason: str) -> Tuple[bool, SubTask]:
        """
        Incrementa el contador de reintentos.
        Si alcanza el límite (3 reintentos), marca la subtarea como 'pivoted' y retorna True.
        """
        for t in self.tasks:
            if t.id == task_id:
                t.retries += 1
                if t.retries >= t.max_retries:
                    t.status = "pivoted"
                    return True, t
                return False, t
        raise ValueError(f"Tarea {task_id} no encontrada en el plan.")

    def is_all_completed(self) -> bool:
        return all(t.status in ["completed", "pivoted"] for t in self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "expected_verification": t.expected_verification,
                    "status": t.status,
                    "retries": t.retries,
                    "dependencies": t.dependencies
                }
                for t in self.tasks
            ]
        }


class DAGPlanner:
    """Generador de planes estructurados mediante Gemini 3.8 Flash."""

    def __init__(self, llm_client: LocalLLMClient):
        self.llm = llm_client

    def create_plan(self, goal: str) -> TaskPlan:
        """Genera el plan descompuesto antes de tocar cualquier herramienta."""
        system_prompt = (
            "Eres el Planificador Estratégico (DAG Planner) de JEV. "
            "Descompón la meta en un conjunto de 2 a 5 micro-tareas secuenciales. "
            "DIRECTIVAS MAESTRAS DE PLANIFICACIÓN:\n"
            "1. Autonomía Estricta: El plan debe ser completamente autónomo y ejecutable de principio a fin de forma continua sin pausas intermedias ni transferir turnos al usuario.\n"
            "2. Higiene de Dependencias (Stdlib First): Prohibido planificar 'pip install' para módulos de la biblioteca estándar de Python (asyncio, socket, threading, dataclasses, argparse, etc.).\n"
            "3. Cada micro-tarea debe tener un criterio claro de verificación objetiva (ej: 'El archivo X existe con >0 bytes', 'El comando devuelve código 0').\n"
            "4. Diseño 3D y CAD: Si la meta pide diseñar, modelar o crear una pieza, producto o escena 3D, planifica como primera micro-tarea invocar la herramienta 'skill_cad_mesh' (piezas paramétricas reales: engranajes, bridas, tuercas, pernos, ejes, carcasas, escuadras, poleas, rodamientos, placas, codos, resortes) o 'render_3d_scene' (escenas declarativas JSON). Nunca planifiques escribir JavaScript dentro de Python, ni wrappers con re.sub, ni duplicar WebGLRenderer/Scene. Usa 'execute_viewport_script' solo para animar la escena activa.\n"
            "Responde ÚNICAMENTE en JSON con el esquema:\n"
            "[\n"
            "  {\n"
            "    \"id\": 1,\n"
            "    \"title\": \"Nombre corto de la micro-tarea\",\n"
            "    \"description\": \"Instrucción detallada de qué hacer\",\n"
            "    \"expected_verification\": \"Cómo comprobar objetivamente el éxito\",\n"
            "    \"dependencies\": []\n"
            "  }\n"
            "]"
        )

        user_prompt = f"Meta del usuario: {goal}"

        try:
            res = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw = res.content.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            items = json.loads(raw)
            subtasks = []
            for item in items:
                subtasks.append(SubTask(
                    id=item.get("id", len(subtasks) + 1),
                    title=item.get("title", f"Subtarea {len(subtasks) + 1}"),
                    description=item.get("description", ""),
                    expected_verification=item.get("expected_verification", "Comprobación estándar"),
                    dependencies=item.get("dependencies", [])
                ))
            return TaskPlan(goal=goal, tasks=subtasks)
        except Exception as e:
            # Plan fallback de 1 paso en caso de error de parseo
            default_subtask = SubTask(
                id=1,
                title="Ejecutar meta directamente",
                description=goal,
                expected_verification="Verificación de resultado de herramientas",
                dependencies=[]
            )
            return TaskPlan(goal=goal, tasks=[default_subtask])
