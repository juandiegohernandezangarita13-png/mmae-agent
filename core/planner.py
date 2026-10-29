import json
import re
from typing import List, Dict, Any
from utils.logger import log

class TaskPlanner:
    """
    Desglosa el plan macro en subtareas atómicas y supervisa su completitud.
    """
    def __init__(self):
        self.tasks: List[Dict[str, Any]] = []
        self.current_index: int = 0

    def parse_tasks_from_skeleton(self, skeleton_text: str) -> List[Dict[str, Any]]:
        self.tasks.clear()
        self.current_index = 0
        
        # Extrae líneas numeradas (ej: "1. Inspeccionar...", "2. Crear archivo...")
        lines = skeleton_text.splitlines()
        task_id = 1
        for line in lines:
            line = line.strip()
            match = re.match(r"^(\d+)[\.\-\)]\s*(.*)", line)
            if match:
                desc = match.group(2).strip()
                if desc:
                    self.tasks.append({
                        "id": task_id,
                        "description": desc,
                        "status": "pending"
                    })
                    task_id += 1

        if not self.tasks:
            # Fallback en caso de que el macro no haya usado numeración
            self.tasks.append({"id": 1, "description": skeleton_text.strip(), "status": "pending"})

        log.info(f"Planificador inicializado con {len(self.tasks)} subtareas.")
        return self.tasks

    def get_next_task(self) -> Dict[str, Any] | None:
        if self.current_index < len(self.tasks):
            return self.tasks[self.current_index]
        return None

    def complete_current_task(self, success: bool = True):
        if self.current_index < len(self.tasks):
            self.tasks[self.current_index]["status"] = "completed" if success else "failed"
            self.current_index += 1

    def is_finished(self) -> bool:
        return self.current_index >= len(self.tasks)
