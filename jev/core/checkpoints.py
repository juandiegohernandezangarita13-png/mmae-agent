"""
Sistema de Checkpoints de Estado y Reanudación Persistente para JEV.
Guarda el estado de la tarea en disco en cada paso validado para permitir
reanudar ejecuciones interrumpidas sin tener que empezar desde cero.
"""
from typing import Dict, Any, Optional, List
import json
import time
from pathlib import Path

from jev.config import default_config


class CheckpointManager:
    """Gestiona el guardado y recuperación de estados de ejecución en disco."""

    def __init__(self, checkpoints_dir: Optional[Path] = None):
        self.checkpoints_dir = checkpoints_dir or (default_config.base_dir / "data" / "checkpoints")
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        task_id: str,
        goal: str,
        plan_dict: Dict[str, Any],
        completed_step_count: int,
        messages: List[Dict[str, Any]]
    ) -> Path:
        """Guarda una instantánea completa del estado de ejecución."""
        checkpoint_file = self.checkpoints_dir / f"checkpoint_{task_id}.json"
        data = {
            "task_id": task_id,
            "timestamp": time.time(),
            "goal": goal,
            "completed_steps": completed_step_count,
            "plan": plan_dict,
            # Guardamos los mensajes truncando outputs excesivos para ahorrar espacio
            "messages": messages[-20:]
        }
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return checkpoint_file

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Carga un checkpoint por ID si existe."""
        checkpoint_file = self.checkpoints_dir / f"checkpoint_{task_id}.json"
        if not checkpoint_file.exists():
            return None
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_latest_resumable_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Busca el checkpoint más reciente que no haya sido completado."""
        files = sorted(self.checkpoints_dir.glob("checkpoint_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as cp:
                    data = json.load(cp)
                    return data
            except Exception:
                continue
        return None

    def clear_checkpoint(self, task_id: str) -> None:
        """Elimina el checkpoint una vez que la tarea ha sido finalizada con éxito."""
        checkpoint_file = self.checkpoints_dir / f"checkpoint_{task_id}.json"
        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
            except Exception:
                pass
