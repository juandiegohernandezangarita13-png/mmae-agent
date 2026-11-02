"""
Módulo de Catálogo, Indexación, Detección de Conflictos y Recuperación Dinámica de Habilidades (Skills).
Permite gestionar miles de Agent Skills oficiales sin saturar la ventana de contexto ni generar contradicciones.
"""
from .catalog_indexer import SkillsCatalogIndexer
from .conflict_resolver import SkillConflictResolver
from .skill_rag import SkillRAG

__all__ = ["SkillsCatalogIndexer", "SkillConflictResolver", "SkillRAG"]
