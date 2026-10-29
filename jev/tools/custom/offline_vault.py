"""
Herramienta de Base de Conocimiento Local y Búsqueda de Texto Completo (OfflineVaultTool).

Gestiona una base de datos SQLite con soporte FTS5 en data/vault.db para
almacenar, indexar y recuperar documentación, fragmentos de código y guías
técnicas de forma 100% autónoma y sin conexión a internet.
"""
from typing import Dict, Any, Optional, List, Literal
from pathlib import Path
import sqlite3
import time
from pydantic import BaseModel, Field, ValidationError

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class OfflineVaultInput(BaseModel):
    """Esquema de parámetros validados con Pydantic para OfflineVaultTool."""
    action: Literal["store", "search", "list", "get", "delete"] = Field(
        description="Operación a realizar: 'store' (guardar/actualizar), 'search' (búsqueda FTS5), 'list' (listar), 'get' (obtener), 'delete' (eliminar)."
    )
    title: Optional[str] = Field(
        default=None,
        description="Título único del documento o snippet técnico."
    )
    content: Optional[str] = Field(
        default=None,
        description="Contenido técnico, código fuente o documentación en texto/markdown."
    )
    tags: Optional[str] = Field(
        default="",
        description="Etiquetas clasificatorias separadas por comas (ej: 'python,api,redes')."
    )
    query: Optional[str] = Field(
        default=None,
        description="Término o consulta para búsqueda de texto completo (FTS5)."
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Límite máximo de registros a retornar en búsquedas o listados."
    )
    entry_id: Optional[int] = Field(
        default=None,
        description="Identificador numérico del registro para operaciones 'get' o 'delete'."
    )


class OfflineVaultTool(BaseTool):
    """
    Herramienta que provee almacenamiento e indexación local FTS5 ultrarrápido
    para snippets, manuales y notas técnicas en data/vault.db.
    """
    name = "offline_vault"
    description = (
        "Base de conocimiento y documentación técnica offline local (SQLite FTS5 en data/vault.db). "
        "Permite almacenar, consultar por texto completo, listar y recuperar snippets y manuales sin internet."
    )
    parameters = OfflineVaultInput.model_json_schema()

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__()
        self.db_path = db_path or (default_config.base_dir / "data" / "vault.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._fts_available = True
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        # WAL mode para lecturas y escrituras concurrentes ultrarrápidas
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_database(self) -> None:
        """Crea las tablas maestras y el índice de búsqueda de texto completo."""
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS vault_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at REAL,
                updated_at REAL
            );
            """)

            # Intentar crear tabla virtual FTS5
            try:
                conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
                    title,
                    content,
                    tags,
                    content='vault_entries',
                    content_rowid='id'
                );
                """)
                # Triggers de sincronización automática FTS5
                conn.execute("""
                CREATE TRIGGER IF NOT EXISTS vault_ai AFTER INSERT ON vault_entries BEGIN
                    INSERT INTO vault_fts(rowid, title, content, tags) VALUES (new.id, new.title, new.content, new.tags);
                END;
                """)
                conn.execute("""
                CREATE TRIGGER IF NOT EXISTS vault_ad AFTER DELETE ON vault_entries BEGIN
                    INSERT INTO vault_fts(vault_fts, rowid, title, content, tags) VALUES('delete', old.id, old.title, old.content, old.tags);
                END;
                """)
                conn.execute("""
                CREATE TRIGGER IF NOT EXISTS vault_au AFTER UPDATE ON vault_entries BEGIN
                    INSERT INTO vault_fts(vault_fts, rowid, title, content, tags) VALUES('delete', old.id, old.title, old.content, old.tags);
                    INSERT INTO vault_fts(rowid, title, content, tags) VALUES (new.id, new.title, new.content, new.tags);
                END;
                """)
                self._fts_available = True
            except sqlite3.OperationalError:
                # Si FTS5 no estuviera habilitado en el binario de sqlite3
                self._fts_available = False

    def execute(
        self,
        action: str = "list",
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[str] = "",
        query: Optional[str] = None,
        limit: int = 10,
        entry_id: Optional[int] = None,
        **kwargs
    ) -> ToolResult:
        try:
            params = OfflineVaultInput(
                action=action,
                title=title,
                content=content,
                tags=tags,
                query=query,
                limit=limit,
                entry_id=entry_id
            )
        except ValidationError as ve:
            return ToolResult(
                success=False,
                output="",
                error=f"Error de validación de parámetros en OfflineVaultTool: {ve}"
            )

        try:
            if params.action == "store":
                return self._store_entry(params.title, params.content, params.tags)
            elif params.action == "search":
                return self._search_entries(params.query, params.limit)
            elif params.action == "list":
                return self._list_entries(params.limit)
            elif params.action == "get":
                return self._get_entry(params.title, params.entry_id)
            elif params.action == "delete":
                return self._delete_entry(params.title, params.entry_id)
            else:
                return ToolResult(success=False, output="", error=f"Acción no soportada: '{params.action}'")
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en OfflineVaultTool: {exc}"
            )

    def _store_entry(self, title: Optional[str], content: Optional[str], tags: Optional[str]) -> ToolResult:
        if not title or not content:
            return ToolResult(
                success=False,
                output="",
                error="Los parámetros 'title' y 'content' son requeridos para la acción 'store'."
            )

        now = time.time()
        clean_tags = (tags or "").strip()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Upsert
            cursor.execute("""
            INSERT INTO vault_entries (title, content, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                content = excluded.content,
                tags = excluded.tags,
                updated_at = excluded.updated_at;
            """, (title, content, clean_tags, now, now))
            row_id = cursor.lastrowid

        return ToolResult(
            success=True,
            output=f"✓ Documento '{title}' almacenado e indexado en vault local (ID: {row_id}, {len(content)} caracteres).",
            data={"title": title, "tags": clean_tags, "size_chars": len(content)}
        )

    def _search_entries(self, query: Optional[str], limit: int) -> ToolResult:
        if not query or not query.strip():
            return ToolResult(
                success=False,
                output="",
                error="El parámetro 'query' es obligatorio para la búsqueda."
            )

        clean_q = query.strip()
        results = []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if self._fts_available:
                try:
                    # Formatear consulta para FTS5
                    fts_q = clean_q.replace("'", "''").replace('"', '""')
                    cursor.execute("""
                    SELECT e.id, e.title, e.tags, snippet(vault_fts, 1, '<b>', '</b>', '...', 20) AS snippet, e.updated_at
                    FROM vault_fts f
                    JOIN vault_entries e ON f.rowid = e.id
                    WHERE vault_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                    """, (f'"{fts_q}"' if " " in fts_q else fts_q + "*", limit))
                    results = cursor.fetchall()
                except sqlite3.OperationalError:
                    results = []

            # Fallback con LIKE si FTS falló o no devolvió resultados
            if not results:
                cursor.execute("""
                SELECT id, title, tags, substr(content, 1, 150) AS snippet, updated_at
                FROM vault_entries
                WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?;
                """, (f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%", limit))
                results = cursor.fetchall()

        if not results:
            return ToolResult(
                success=True,
                output=f"No se encontraron documentos coincidentes con la consulta '{query}'.",
                data={"results_count": 0, "query": query}
            )

        lines = [f"📚 [RESULTADOS OFFLINE VAULT - BÚSQUEDA '{query}'] (Total: {len(results)})"]
        formatted_list = []
        for r in results:
            date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(r['updated_at']))
            lines.append(f"• ID {r['id']} | [{r['title']}] (Tags: {r['tags'] or 'ninguno'}, {date_str})")
            lines.append(f"  Snippet: {r['snippet']}")
            formatted_list.append({
                "id": r["id"],
                "title": r["title"],
                "tags": r["tags"],
                "snippet": r["snippet"]
            })

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"results": formatted_list, "count": len(results)}
        )

    def _list_entries(self, limit: int) -> ToolResult:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, title, tags, length(content) AS size_chars, updated_at
            FROM vault_entries
            ORDER BY updated_at DESC
            LIMIT ?;
            """, (limit,))
            rows = cursor.fetchall()

        if not rows:
            return ToolResult(
                success=True,
                output="El vault local está actualmente vacío. Puedes guardar documentos con action='store'.",
                data={"total": 0}
            )

        lines = [f"📂 [DOCUMENTOS DISPONIBLES EN EL VAULT OFFLINE] (Mostrando {len(rows)}):"]
        items = []
        for r in rows:
            date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(r['updated_at']))
            lines.append(f"• ID {r['id']}: '{r['title']}' ({r['size_chars']} caracteres | Tags: {r['tags'] or '-'} | {date_str})")
            items.append({"id": r["id"], "title": r["title"], "tags": r["tags"], "size": r["size_chars"]})

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"entries": items, "count": len(rows)}
        )

    def _get_entry(self, title: Optional[str], entry_id: Optional[int]) -> ToolResult:
        if not title and entry_id is None:
            return ToolResult(
                success=False,
                output="",
                error="Debes proporcionar 'title' o 'entry_id' para recuperar el documento."
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if entry_id is not None:
                cursor.execute("SELECT * FROM vault_entries WHERE id = ?;", (entry_id,))
            else:
                cursor.execute("SELECT * FROM vault_entries WHERE title = ?;", (title,))
            row = cursor.fetchone()

        if not row:
            return ToolResult(
                success=False,
                output="",
                error=f"No se encontró ningún documento con título='{title}' o ID={entry_id}."
            )

        date_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['updated_at']))
        out = (
            f"📄 [VAULT DOCUMENT: {row['title']}]\n"
            f"• ID: {row['id']} | Tags: {row['tags'] or '-'} | Actualizado: {date_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{row['content']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return ToolResult(
            success=True,
            output=out,
            data={
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "tags": row["tags"],
                "updated_at": row["updated_at"]
            }
        )

    def _delete_entry(self, title: Optional[str], entry_id: Optional[int]) -> ToolResult:
        if not title and entry_id is None:
            return ToolResult(
                success=False,
                output="",
                error="Debes proporcionar 'title' o 'entry_id' para eliminar el documento."
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if entry_id is not None:
                cursor.execute("DELETE FROM vault_entries WHERE id = ?;", (entry_id,))
            else:
                cursor.execute("DELETE FROM vault_entries WHERE title = ?;", (title,))
            affected = cursor.rowcount

        if affected == 0:
            return ToolResult(
                success=False,
                output="",
                error=f"No se encontró el documento especificado para eliminar."
            )

        return ToolResult(
            success=True,
            output=f"✓ Documento eliminado exitosamente del vault.",
            data={"affected_rows": affected}
        )
