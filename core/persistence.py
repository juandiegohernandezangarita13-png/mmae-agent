import json
import os
from typing import Dict, Any, List
from utils.logger import log

class StatePersistence:
    """
    Guarda y recupera el estado del agente, contexto acumulado y lecciones aprendidas en disco.
    """
    def __init__(self, storage_path: str = ".mmae_state.json"):
        self.storage_path = os.path.abspath(storage_path)

    def save_state(self, state_data: Dict[str, Any]) -> bool:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            log.info(f"Estado persistido con éxito en {self.storage_path}")
            return True
        except Exception as e:
            log.error(f"Fallo al guardar estado persistente: {str(e)}")
            return False

    def load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.storage_path):
            return {"history": [], "learned_lessons": [], "env_vars": {}}
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Fallo al cargar estado previo: {str(e)}")
            return {"history": [], "learned_lessons": [], "env_vars": {}}
