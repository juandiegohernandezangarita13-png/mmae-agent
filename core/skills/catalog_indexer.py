"""
Indexador y constructor de base de datos local para el catálogo de Agent Skills.
Parsea repositorios de habilidades curadas (como awesome-agent-skills) y genera
un índice FTS5 en SQLite y JSON para búsqueda sub-milisegundo.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .conflict_resolver import SkillConflictResolver

logger = logging.getLogger("jev.skills.indexer")


class SkillsCatalogIndexer:
    """
    Parsea, clasifica e indexa colecciones masivas de habilidades para agentes.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (self.base_dir / "data" / "skills_catalog")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "skills.sqlite"
        self.json_path = self.data_dir / "skills_index.json"
        self.seed_path = Path(__file__).resolve().parent / "catalog_seed.json"

    def bootstrap_from_seed_if_needed(self) -> bool:
        """Si la base de datos SQLite no existe, la inicializa desde el archivo semilla catalog_seed.json."""
        if self.db_path.exists():
            return True
        if self.seed_path.exists():
            try:
                with open(self.seed_path, "r", encoding="utf-8") as f:
                    skills = json.load(f)
                self._save_to_sqlite(skills)
                return True
            except Exception as e:
                logger.error(f"Fallo al cargar catálogo semilla: {e}")
        return False

    def index_markdown_catalog(self, readme_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Lee el archivo README.md de habilidades e indexa todas las entradas en SQLite y JSON.
        """
        if readme_path is None:
            readme_path = self.base_dir / "repos" / "awesome-agent-skills" / "README.md"

        if not readme_path.exists():
            return {
                "status": "error",
                "message": f"Archivo de habilidades no encontrado en: {readme_path}"
            }

        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Regex flexible para capturar items de lista con enlaces a skills
        pattern = re.compile(
            r'^\s*[-*]\s+(?:\*\*)?\[([^\]]+)\]\((https?://[^)]+)\)(?:\*\*)?\s*[-:—]\s*(.+)$',
            re.MULTILINE
        )
        matches = pattern.findall(content)

        skills_dict: Dict[str, Dict[str, Any]] = {}

        for skill_id, url, desc in matches:
            skill_id = skill_id.strip()
            desc = desc.strip()
            url = url.strip()

            if "/" in skill_id:
                owner, name = skill_id.split("/", 1)
            else:
                owner = "community"
                name = skill_id

            category, tags, conflict_domain = SkillConflictResolver.assign_domain_and_tags(
                skill_id, name, desc
            )

            # Deduplicar si ya existe
            if skill_id not in skills_dict:
                skills_dict[skill_id] = {
                    "skill_id": skill_id,
                    "name": name,
                    "owner": owner,
                    "category": category,
                    "description": desc,
                    "url": url,
                    "tags": tags,
                    "conflict_domain": conflict_domain
                }

        skills_list = list(skills_dict.values())

        # Guardar en JSON
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(skills_list, f, ensure_ascii=False, indent=2)

        # Guardar en SQLite con FTS5
        self._save_to_sqlite(skills_list)

        return {
            "status": "success",
            "total_skills_indexed": len(skills_list),
            "db_path": str(self.db_path),
            "json_path": str(self.json_path),
            "categories_count": len({s["category"] for s in skills_list})
        }

    def _save_to_sqlite(self, skills: List[Dict[str, Any]]) -> None:
        """Crea tablas relacionales y virtuales FTS5 para búsqueda rápida."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("DROP TABLE IF EXISTS skills;")
        cur.execute("DROP TABLE IF EXISTS skills_fts;")

        cur.execute("""
            CREATE TABLE skills (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                url TEXT NOT NULL,
                tags TEXT NOT NULL,
                conflict_domain TEXT
            );
        """)

        cur.execute("""
            CREATE VIRTUAL TABLE skills_fts USING fts5(
                skill_id,
                name,
                owner,
                category,
                description,
                tags,
                content='skills',
                content_rowid='rowid'
            );
        """)

        cur.executemany("""
            INSERT INTO skills (skill_id, name, owner, category, description, url, tags, conflict_domain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, [
            (
                s["skill_id"],
                s["name"],
                s["owner"],
                s["category"],
                s["description"],
                s["url"],
                json.dumps(s["tags"]),
                s["conflict_domain"]
            )
            for s in skills
        ])

        cur.execute("""
            INSERT INTO skills_fts(skills_fts) VALUES('rebuild');
        """)

        conn.commit()
        conn.close()
        logger.info(f"{len(skills)} habilidades indexadas con FTS5 en {self.db_path}")
