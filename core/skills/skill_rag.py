"""
Motor de Búsqueda y Recuperación de Habilidades (Skill RAG).
Permite buscar habilidades mediante SQLite FTS5 y ranking BM25,
aplicando resolución de conflictos semánticos en tiempo real.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .conflict_resolver import SkillConflictResolver

logger = logging.getLogger("jev.skills.rag")


class SkillRAG:
    """
    Recuperador dinámico de habilidades sobre demanda para el ciclo cognitivo del agente.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (self.base_dir / "data" / "skills_catalog")
        self.db_path = self.data_dir / "skills.sqlite"
        if not self.db_path.exists():
            from .catalog_indexer import SkillsCatalogIndexer
            SkillsCatalogIndexer(data_dir=self.data_dir).bootstrap_from_seed_if_needed()

    def search(
        self,
        query: str,
        limit: int = 5,
        resolve_conflicts: bool = True,
        workspace_stack: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca habilidades coincidentes con la consulta, puntuadas por relevancia BM25.
        """
        if not self.db_path.exists():
            logger.warning(f"Base de datos de habilidades no existe en: {self.db_path}")
            return []

        clean_query = self._sanitize_fts_query(query)
        if not clean_query:
            return []

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT 
                    s.skill_id,
                    s.name,
                    s.owner,
                    s.category,
                    s.description,
                    s.url,
                    s.tags,
                    s.conflict_domain,
                    bm25(skills_fts) as rank
                FROM skills_fts f
                JOIN skills s ON f.rowid = s.rowid
                WHERE skills_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
            """, (clean_query, limit * 3))  # Traer extra para permitir filtrado de conflictos

            rows = cur.fetchall()
            candidates = []
            for r in rows:
                try:
                    tags = json.loads(r[6])
                except Exception:
                    tags = []
                candidates.append({
                    "skill_id": r[0],
                    "name": r[1],
                    "owner": r[2],
                    "category": r[3],
                    "description": r[4],
                    "url": r[5],
                    "tags": tags,
                    "conflict_domain": r[7],
                    "rank_score": abs(float(r[8]))
                })

            if resolve_conflicts:
                filtered = SkillConflictResolver.resolve_conflicts(
                    candidates,
                    context_hint=query,
                    workspace_tech_stack=workspace_stack
                )
                return filtered[:limit]

            return candidates[:limit]

        except Exception as e:
            logger.error(f"Error en búsqueda FTS de skills para '{query}': {e}")
            return []
        finally:
            conn.close()

    def get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Recupera la ficha completa de una habilidad por su identificador único."""
        if not self.db_path.exists():
            return None

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT skill_id, name, owner, category, description, url, tags, conflict_domain
                FROM skills
                WHERE skill_id = ?;
            """, (skill_id,))
            row = cur.fetchone()
            if not row:
                return None
            try:
                tags = json.loads(row[6])
            except Exception:
                tags = []
            return {
                "skill_id": row[0],
                "name": row[1],
                "owner": row[2],
                "category": row[3],
                "description": row[4],
                "url": row[5],
                "tags": tags,
                "conflict_domain": row[7]
            }
        finally:
            conn.close()

    def format_skills_for_prompt(self, skills: List[Dict[str, Any]]) -> str:
        """
        Formatea las habilidades encontradas en un bloque conciso listo para inyección en el prompt.
        """
        if not skills:
            return ""

        lines = ["\n[HABILIDADES EXTERNAS RECUPERADAS (OFFICIAL SKILLS)]:"]
        for s in skills:
            lines.append(
                f" • **{s['skill_id']}** ({s['category']}): {s['description']}\n"
                f"   [Referencia Oficial]: {s['url']}"
            )
        return "\n".join(lines)

    def _sanitize_fts_query(self, query: str) -> str:
        """Limpia caracteres de puntuación especiales que SQLite FTS5 interpreta como sintaxis."""
        tokens = [t.strip() for t in query.split() if len(t.strip()) > 1]
        if not tokens:
            return ""
        # Buscar palabras clave con operador OR para máxima cobertura
        clean_tokens = [re.sub(r'[^a-zA-Z0-9_\-]', '', t) for t in tokens]
        clean_tokens = [t for t in clean_tokens if t]
        if not clean_tokens:
            return ""
        return " OR ".join(clean_tokens)
