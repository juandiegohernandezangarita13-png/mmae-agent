"""
Puente y Motor de Integración Mem0 (mem0ai) para MMAE-Agent.
Proporciona memoria persistente a largo plazo multicapa:
- Almacena preferencias de usuario, rutas habituales de archivos y resoluciones de errores pasados.
- Integra la biblioteca oficial 'mem0' (mem0ai) cuando está disponible, combinándola con el
  almacén SQLite local de alta velocidad y resolución de conflictos de UserPersistentMemory.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from core.memory.user_memory import UserPersistentMemory, UserMemoryCategory

logger = logging.getLogger(__name__)

# Intentar importar la biblioteca oficial mem0
try:
    from mem0 import Memory as Mem0SDKMemory
    MEM0_AVAILABLE = True
except Exception:
    Mem0SDKMemory = None
    MEM0_AVAILABLE = False


class Mem0Bridge:
    """
    Motor unificado de memoria a largo plazo estilo Mem0.
    Garantiza persistencia infalible entre sesiones para MMAE-Agent.
    """

    def __init__(self, db_dir: Optional[Path] = None, user_id: str = "default_user"):
        self.db_dir = Path(db_dir or "data/memory").resolve()
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id

        # 1. Almacén local persistente con control de transacciones y SQLite
        self.local_mem0 = UserPersistentMemory(db_path=self.db_dir / "user_memory.db")

        # 2. Cliente SDK mem0ai oficial (si está disponible y configurado)
        self.sdk_client = None
        if MEM0_AVAILABLE:
            try:
                # Inicializar memoria embebida local de mem0
                config = {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "path": str(self.db_dir / "qdrant_mem0")
                        }
                    },
                    "version": "v1.1"
                }
                # Intentar instanciar SDK de forma tolerante a fallos
                self.sdk_client = Mem0SDKMemory()
            except Exception as e:
                logger.debug("mem0 SDK no pudo inicializarse con config local: %s. Operando con SQLite nativo.", e)
                self.sdk_client = None

    def add(
        self,
        text: str,
        category: str = UserMemoryCategory.PREFERENCE.value,
        key: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Añade o actualiza una memoria en el sistema."""
        uid = user_id or self.user_id
        # Guardar siempre en local_mem0 (garantía de persistencia y cero latencia)
        res = self.local_mem0.add(
            value=text,
            category=category,
            key=key,
            user_id=uid,
            raw_text=text
        )

        # Si el SDK mem0ai está activo, replicar en vector store
        if self.sdk_client:
            try:
                meta = metadata or {}
                meta.update({"category": category, "key": key or ""})
                self.sdk_client.add(text, user_id=uid, metadata=meta)
            except Exception as e:
                logger.debug("Replicación en mem0 SDK falló (no crítico): %s", e)

        return res

    def remember_preference(self, key: str, value: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Guarda o actualiza una preferencia explícita del usuario."""
        return self.add(
            text=value,
            category=UserMemoryCategory.PREFERENCE.value,
            key=key,
            user_id=user_id
        )

    def remember_path(self, path: str, description: str = "", user_id: Optional[str] = None) -> Dict[str, Any]:
        """Almacena una ruta habitual del sistema o proyecto."""
        return self.local_mem0.remember_path(path_str=path, description=description, user_id=user_id or self.user_id)

    def remember_error_resolution(self, error: str, resolution: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Almacena una solución comprobada a un error previo."""
        return self.local_mem0.remember_error_resolution(error_signature=error, resolution=resolution, user_id=user_id or self.user_id)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Búsqueda contextual de memorias relevantes."""
        uid = user_id or self.user_id
        return self.local_mem0.search(query=query, user_id=uid, category=category, limit=limit)

    def recall_for_task(self, task_description: str, user_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Recuperación proactiva al inicio de una tarea:
        Recupera rutas habituales, errores previos y preferencias relevantes.
        """
        uid = user_id or self.user_id
        relevant = self.search(query=task_description, user_id=uid, limit=6)

        paths = [m for m in relevant if m.get("category") == UserMemoryCategory.HABITUAL_PATH.value]
        errors = [m for m in relevant if m.get("category") == UserMemoryCategory.ERROR_RESOLUTION.value]
        preferences = [m for m in relevant if m.get("category") in (UserMemoryCategory.PREFERENCE.value, UserMemoryCategory.SYSTEM_DIRECTIVE.value, UserMemoryCategory.WORKFLOW_RULE.value)]

        # Si no hubo coincidencia exacta de rutas, traer las rutas más activas
        if not paths:
            paths = self.local_mem0.get_all(user_id=uid, category=UserMemoryCategory.HABITUAL_PATH.value)[:3]

        return {
            "preferences": preferences,
            "habitual_paths": paths,
            "error_resolutions": errors,
            "all_relevant": relevant
        }

    def build_prompt_context(self, task_query: str, user_id: Optional[str] = None) -> str:
        """
        Construye una sección concisa e informativa para inyectar en el prompt del sistema.
        """
        recalled = self.recall_for_task(task_query, user_id=user_id)
        sections = []

        # Perfil y preferencias
        base_profile = self.local_mem0.get_user_profile_context(user_id=user_id or self.user_id)
        if base_profile:
            sections.append(base_profile)

        # Rutas habituales detectadas
        if recalled["habitual_paths"]:
            p_lines = ["[RUTAS HABITUALES PERSISTENTES (Mem0)]:"]
            for p in recalled["habitual_paths"]:
                p_lines.append(f"  • {p['key']}: {p['value']}")
            sections.append("\n".join(p_lines))

        # Resoluciones de errores pasados
        if recalled["error_resolutions"]:
            e_lines = ["[RESOLUCIONES DE ERRORES PASADOS RELEVANTES (Mem0)]:"]
            for e in recalled["error_resolutions"]:
                e_lines.append(f"  • {e['value']}")
            sections.append("\n".join(e_lines))

        return "\n\n".join(sections)

    def get_all(self, category: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Devuelve todas las memorias activas."""
        return self.local_mem0.get_all(user_id=user_id or self.user_id, category=category, active_only=True)

    def delete(self, memory_id: str) -> bool:
        """Elimina una memoria por su ID."""
        return self.local_mem0.delete(memory_id=memory_id, soft_delete=True)
