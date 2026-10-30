"""
Grafo de Conocimiento Temporal con Control de Validez (Inspirado en Graffiti).
Permite modelar entidades y relaciones temporales: saber cuándo un hecho fue válido,
cuándo expiró o fue reemplazado (valid_from, valid_to, is_current), evitando alucinaciones
y obsolescencia de información en el agente.
"""
import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple


class TemporalKnowledgeGraph:
    """
    Motor de Grafo de Conocimiento Temporal (TKG) estilo Graffiti:
    - Nodos: Entidades tipadas (Usuario, Herramienta, Proyecto, Framework, etc.)
    - Aristas: Relaciones con intervalo de validez [valid_from, valid_to] y flag is_current.
    - Invalidación automática: Al declarar un nuevo hecho funcional, el hecho previo expira con fecha exacta.
    - Consultas Point-in-time ('query_as_of'): Permite viajar en el tiempo y consultar el estado exacto en una fecha.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path("data/memory") / "temporal_knowledge_graph.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            # Nodos de entidades
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temporal_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT UNIQUE NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'Entity',
                    name TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Aristas de relaciones temporales
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temporal_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_node TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_node TEXT NOT NULL,
                    valid_from DATETIME NOT NULL,
                    valid_to DATETIME,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    evidence TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_temporal_edges_query
                ON temporal_edges (source_node, relation, is_current)
            """)
            conn.commit()

    def add_entity(
        self,
        node_id: str,
        name: str,
        entity_type: str = "Entity",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        clean_id = node_id.strip()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO temporal_nodes (node_id, entity_type, name, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    name = excluded.name,
                    entity_type = excluded.entity_type,
                    metadata_json = excluded.metadata_json
            """, (clean_id, entity_type, name, json.dumps(metadata or {}, ensure_ascii=False)))
            conn.commit()

    def add_relation(
        self,
        source: str,
        relation: str,
        target: str,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
        is_functional: bool = True,
        confidence: float = 1.0,
        evidence: str = ""
    ) -> int:
        """
        Registra una relación temporal (Graffiti Pattern).
        Si is_functional=True (p.ej. 'current_framework', 'preferred_model', 'active_project'),
        invalida automáticamente la relación previa marcándola con valid_to = now() e is_current = 0.
        """
        now = datetime.now()
        vf = (valid_from or now).isoformat()
        vt = valid_to.isoformat() if valid_to else None

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Asegurar existencia básica de nodos
            cursor.execute("INSERT OR IGNORE INTO temporal_nodes (node_id, entity_type, name) VALUES (?, 'Entity', ?)", (source, source))
            cursor.execute("INSERT OR IGNORE INTO temporal_nodes (node_id, entity_type, name) VALUES (?, 'Entity', ?)", (target, target))

            if is_functional:
                # Invalidar hechos vigentes previos con la misma relación funcional
                cursor.execute("""
                    UPDATE temporal_edges
                    SET valid_to = ?, is_current = 0
                    WHERE source_node = ? AND relation = ? AND is_current = 1 AND target_node != ?
                """, (vf, source, relation, target))

            # Insertar nueva relación activa
            cursor.execute("""
                INSERT INTO temporal_edges
                (source_node, relation, target_node, valid_from, valid_to, is_current, confidence, evidence)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """, (source, relation, target, vf, vt, confidence, evidence))

            edge_id = cursor.lastrowid
            conn.commit()
            return edge_id

    def invalidate_relation(
        self,
        source: str,
        relation: str,
        target: Optional[str] = None,
        invalid_at: Optional[datetime] = None
    ) -> int:
        """Marca una relación como expirada / no válida a partir de una fecha."""
        exp_time = (invalid_at or datetime.now()).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                UPDATE temporal_edges
                SET valid_to = ?, is_current = 0
                WHERE source_node = ? AND relation = ? AND is_current = 1
            """
            params = [exp_time, source, relation]
            if target:
                query += " AND target_node = ?"
                params.append(target)

            cursor.execute(query, params)
            count = cursor.rowcount
            conn.commit()
            return count

    def get_current_facts(
        self,
        source: Optional[str] = None,
        relation: Optional[str] = None,
        target: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Obtiene únicamente hechos que están actualmente vigentes (is_current = 1)."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM temporal_edges WHERE is_current = 1"
            params: List[Any] = []

            if source:
                query += " AND source_node = ?"
                params.append(source)
            if relation:
                query += " AND relation = ?"
                params.append(relation)
            if target:
                query += " AND target_node = ?"
                params.append(target)

            query += " ORDER BY valid_from DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def query_as_of(
        self,
        as_of_time: datetime,
        source: Optional[str] = None,
        relation: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Consulta retrospectiva (Point-in-time Snapshot):
        Recupera los hechos que eran ciertos en una fecha específica del pasado.
        valid_from <= as_of_time AND (valid_to IS NULL OR valid_to > as_of_time)
        """
        target_iso = as_of_time.isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM temporal_edges
                WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
            """
            params: List[Any] = [target_iso, target_iso]

            if source:
                query += " AND source_node = ?"
                params.append(source)
            if relation:
                query += " AND relation = ?"
                params.append(relation)

            query += " ORDER BY valid_from DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_entity_history(self, source: str, relation: Optional[str] = None) -> List[Dict[str, Any]]:
        """Línea de tiempo cronológica completa de relaciones de una entidad (activas y expiradas)."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM temporal_edges WHERE source_node = ?"
            params: List[Any] = [source]

            if relation:
                query += " AND relation = ?"
                params.append(relation)

            query += " ORDER BY valid_from ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_temporal_context_summary(self, focus_source: Optional[str] = None) -> str:
        """Construye un bloque de contexto temporal para el agente."""
        facts = self.get_current_facts(source=focus_source)
        if not facts:
            return ""

        lines = ["[GRAFO DE CONOCIMIENTO TEMPORAL ACTIVO (Graffiti TKG)] :"]
        for f in facts:
            lines.append(
                f"- ({f['source_node']}) --[{f['relation']}]--> ({f['target_node']}) "
                f"[Válido desde: {f['valid_from'][:10]}, Confianza: {f['confidence']:.2f}]"
            )
        return "\n".join(lines)
