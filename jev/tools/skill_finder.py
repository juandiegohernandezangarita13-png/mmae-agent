"""
Herramienta de búsqueda, inspección y carga dinámica de habilidades oficiales (Agent Skills).
Permite a MMAE / JEV descubrir y activar capacidades de ingeniería, DevOps, seguridad y frontend
provenientes de más de 1,230 habilidades curadas sin saturar el contexto.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
from jev.tools.base import BaseTool
from core.skills.skill_rag import SkillRAG
from core.skills.catalog_indexer import SkillsCatalogIndexer


class FindSkillTool(BaseTool):
    """
    Herramienta para buscar y cargar habilidades curadas de forma no contradictoria.
    """

    def __init__(self):
        super().__init__()
        self.rag = SkillRAG()
        self.indexer = SkillsCatalogIndexer()

    @property
    def name(self) -> str:
        return "find_skill"

    @property
    def description(self) -> str:
        return (
            "Busca y recupera habilidades de ingeniería, automatización y desarrollo entre "
            "más de 1,230 Agent Skills oficiales (Anthropic, Supabase, Google, Stripe, Microsoft, etc.). "
            "Aplica resolución automática de conflictos para evitar instrucciones contradictorias."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda o necesidad de ingeniería (ej: 'github automated releases', 'playwright testing', 'docker deploy', 'postgresql migrations')"
                },
                "skill_id": {
                    "type": "string",
                    "description": "Identificador exacto de una habilidad para inspección detallada (ej: 'anthropics/docx', 'callstackincubator/github')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de habilidades a devolver (máximo 5 para conservar tokens)",
                    "default": 3
                },
                "reindex": {
                    "type": "boolean",
                    "description": "Si es True, reconstruye el índice SQLite FTS5 desde el catálogo",
                    "default": False
                }
            }
        }

    def execute(self, **kwargs) -> str:
        if kwargs.get("reindex"):
            res = self.indexer.index_markdown_catalog()
            return json.dumps(res, ensure_ascii=False, indent=2)

        skill_id = kwargs.get("skill_id", "").strip()
        if skill_id:
            skill = self.rag.get_skill_by_id(skill_id)
            if not skill:
                return json.dumps({
                    "status": "not_found",
                    "message": f"Habilidad '{skill_id}' no encontrada en el catálogo."
                }, ensure_ascii=False)
            return json.dumps({
                "status": "success",
                "skill": skill
            }, ensure_ascii=False, indent=2)

        query = kwargs.get("query", "").strip()
        if not query:
            return json.dumps({
                "status": "error",
                "message": "Se requiere proporcionar 'query' o 'skill_id'."
            }, ensure_ascii=False)

        limit = min(int(kwargs.get("limit", 3)), 5)
        skills = self.rag.search(query=query, limit=limit, resolve_conflicts=True)

        if not skills:
            return json.dumps({
                "status": "no_results",
                "query": query,
                "message": "No se encontraron habilidades específicas para esta consulta."
            }, ensure_ascii=False)

        return json.dumps({
            "status": "success",
            "query": query,
            "count": len(skills),
            "skills": skills,
            "prompt_injection": self.rag.format_skills_for_prompt(skills)
        }, ensure_ascii=False, indent=2)
