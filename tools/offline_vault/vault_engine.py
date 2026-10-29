"""
Módulo de Base de Conocimiento Local y Motor de Vault Offline.
Utiliza SQLite FTS5 para indexar, almacenar y consultar manuales técnicos,
código y documentación sin requerir conexión a internet ni dependencias externas.
"""
from typing import List, Dict, Any, Optional
import sqlite3
import json
import os
import argparse
from pathlib import Path


class OfflineVaultEngine:
    """Gestor de base de conocimiento local con capacidades de búsqueda de texto completo (FTS5)."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(__file__).parent
            self.db_path = str(base_dir / "knowledge_vault.db")
        else:
            self.db_path = db_path
        self._init_database()

    def _execute(self, query: str, params: tuple = ()):
        """Helper para ejecutar queries garantizando el cierre de conexión."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        finally:
            conn.close()

    def _init_database(self) -> None:
        """Crea las tablas relacionales y el índice FTS5 si no existen."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                cursor = conn.cursor()
                # Tabla principal de documentos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        tags TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        content TEXT NOT NULL
                    );
                """)

                # Tabla virtual FTS5 para búsquedas ultrarrápidas con ranking
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                        title,
                        content,
                        tags,
                        content='documents',
                        content_rowid='id'
                    );
                """)

                # Triggers para sincronización automática entre documents y documents_fts
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                        INSERT INTO documents_fts(rowid, title, content, tags) 
                        VALUES (new.id, new.title, new.content, new.tags);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                        INSERT INTO documents_fts(documents_fts, rowid, title, content, tags) 
                        VALUES('delete', old.id, old.title, old.content, old.tags);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                        INSERT INTO documents_fts(documents_fts, rowid, title, content, tags) 
                        VALUES('delete', old.id, old.title, old.content, old.tags);
                        INSERT INTO documents_fts(rowid, title, content, tags) 
                        VALUES (new.id, new.title, new.content, new.tags);
                    END;
                """)
        finally:
            conn.close()

    def ingest(self, title: str, content: str, category: str = "general", tags: Optional[List[str]] = None) -> int:
        """Inserta e indexa un nuevo artículo técnico o snippet en el vault."""
        tags_str = ",".join(tags) if tags else ""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO documents (title, category, tags, content) VALUES (?, ?, ?, ?)",
                    (title, category, tags_str, content)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    def ingest_file(self, file_path: Path, category: str = "doc", tags: Optional[List[str]] = None) -> int:
        """Lee un archivo local de texto o código y lo indexa."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        content = path.read_text(encoding="utf-8", errors="ignore")
        title = path.stem.replace("_", " ").title()
        return self.ingest(title=title, content=content, category=category, tags=tags)

    def query_vault(self, topic: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca artículos usando FTS5 con relevancia BM25.
        Soporta operadores booleanos y prefijos (ej: 'wifi*', 'python AND sandbox').
        """
        sanitized_query = topic.strip()
        if not sanitized_query:
            return []

        tokens = sanitized_query.replace('"', '').split()
        match_query = " ".join([f'"{tok}"*' for tok in tokens if tok])

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT 
                        d.id, 
                        d.title, 
                        d.category, 
                        d.tags, 
                        d.created_at,
                        snippet(documents_fts, 1, '<b>', '</b>', '...', 32) as snippet_text,
                        bm25(documents_fts) as score
                    FROM documents_fts f
                    JOIN documents d ON d.id = f.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY score
                    LIMIT ?;
                """, (match_query, limit))
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                cursor.execute("""
                    SELECT id, title, category, tags, created_at, substr(content, 1, 150) as snippet_text, 0 as score
                    FROM documents
                    WHERE title LIKE ? OR content LIKE ?
                    LIMIT ?;
                """, (f"%{sanitized_query}%", f"%{sanitized_query}%", limit))
                rows = cursor.fetchall()

            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "tags": r["tags"].split(",") if r["tags"] else [],
                    "snippet": r["snippet_text"],
                    "score": round(float(r["score"]), 3)
                })
            return results
        finally:
            conn.close()

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Recupera el contenido íntegro de un documento por su ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, category, tags, created_at, content FROM documents WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "title": row["title"],
                    "category": row["category"],
                    "tags": row["tags"].split(",") if row["tags"] else [],
                    "created_at": row["created_at"],
                    "content": row["content"]
                }
            return None
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Devuelve el total de documentos almacenados y categorías."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents;")
            total_docs = cursor.fetchone()[0]
            cursor.execute("SELECT DISTINCT category FROM documents;")
            categories = [r[0] for r in cursor.fetchall()]
            return {
                "total_documents": total_docs,
                "categories": categories,
                "database_path": self.db_path
            }
        finally:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline Vault & Knowledge Engine")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingestar documento")
    p_ingest.add_argument("--title", required=True, help="Título del artículo")
    p_ingest.add_argument("--content", help="Contenido en texto")
    p_ingest.add_argument("--file", help="Ruta a archivo de texto a indexar")
    p_ingest.add_argument("--category", default="general", help="Categoría")
    p_ingest.add_argument("--tags", nargs="*", default=[], help="Etiquetas")

    # Search
    p_search = subparsers.add_parser("search", help="Consultar base de conocimiento")
    p_search.add_argument("query", help="Términos de búsqueda")
    p_search.add_argument("--limit", type=int, default=5, help="Límite de resultados")

    # Read
    p_read = subparsers.add_parser("read", help="Leer documento por ID")
    p_read.add_argument("id", type=int, help="ID del documento")

    # Stats
    subparsers.add_parser("stats", help="Estadísticas de la base de datos")

    args = parser.parse_args()
    engine = OfflineVaultEngine()

    if args.command == "ingest":
        if args.file:
            doc_id = engine.ingest_file(Path(args.file), category=args.category, tags=args.tags)
        elif args.content:
            doc_id = engine.ingest(title=args.title, content=args.content, category=args.category, tags=args.tags)
        else:
            print("Error: Proporcione --content o --file")
            exit(1)
        print(f"[OK] Documento indexado con ID: {doc_id}")

    elif args.command == "search":
        results = engine.query_vault(args.query, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "read":
        doc = engine.get_document(args.id)
        if doc:
            print(f"=== {doc['title']} ===")
            print(doc["content"])
        else:
            print("Documento no encontrado.")

    elif args.command == "stats":
        print(json.dumps(engine.get_stats(), indent=2))
    else:
        parser.print_help()
