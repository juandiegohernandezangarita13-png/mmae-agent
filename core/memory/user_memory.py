"""
Capa de Memoria Persistente de Usuario (Inspirada en Mem0).
Gestiona preferencias de usuario a largo plazo, hechos personales, directivas operativas
y reglas de flujo de trabajo, con resolución automática de conflictos y persistencia en SQLite.
"""
import sqlite3
import hashlib
import json
import re
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class UserMemoryCategory(str, Enum):
    PREFERENCE = "preference"
    PERSONAL_FACT = "personal_fact"
    SYSTEM_DIRECTIVE = "system_directive"
    PROJECT_CONTEXT = "project_context"
    WORKFLOW_RULE = "workflow_rule"


class UserPersistentMemory:
    """
    Memoria de usuario a largo plazo con capacidades estilo Mem0:
    - Adición y extracción de hechos y preferencias
    - Resolución de conflictos (actualización inteligente ante cambios del usuario)
    - Registro de auditoría histórica para no perder información pasada
    - Búsqueda contextual y exportación para inyección en prompts del agente
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path("data/memory") / "user_memory.db")
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
            # Tabla principal de hechos y preferencias activas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    raw_text TEXT,
                    confidence REAL DEFAULT 1.0,
                    update_count INTEGER DEFAULT 0,
                    access_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_memories_user_key 
                ON user_memories (user_id, category, key)
            """)

            # Historial de cambios (Mem0 audit trail / deduplicación con preservación histórica)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT
                )
            """)
            conn.commit()

    @staticmethod
    def _generate_memory_id(user_id: str, category: str, key: str) -> str:
        digest = hashlib.sha256(f"{user_id}:{category}:{key.lower().strip()}".encode("utf-8")).hexdigest()
        return f"mem_{digest[:16]}"

    def add(
        self,
        value: str,
        category: str = UserMemoryCategory.PREFERENCE.value,
        key: Optional[str] = None,
        user_id: str = "default_user",
        confidence: float = 1.0,
        raw_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Añade o actualiza una memoria de usuario.
        Aplica resolución de conflictos: si el usuario cambia una preferencia existente,
        registra el valor antiguo en el historial y actualiza el valor activo.
        """
        clean_val = value.strip()
        clean_key = (key or self._derive_key_from_value(clean_val)).lower().strip()
        mem_id = self._generate_memory_id(user_id, category, clean_key)
        now_iso = datetime.now().isoformat()

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value, update_count, confidence FROM user_memories WHERE memory_id = ? AND is_active = 1",
                (mem_id,)
            )
            existing = cursor.fetchone()

            if existing:
                old_val = existing["value"]
                if old_val != clean_val:
                    # Conflicto detectado: registrar en historial y actualizar
                    cursor.execute("""
                        INSERT INTO user_memory_history (memory_id, user_id, old_value, new_value, reason)
                        VALUES (?, ?, ?, ?, ?)
                    """, (mem_id, user_id, old_val, clean_val, "preference_update_conflict_resolved"))

                    cursor.execute("""
                        UPDATE user_memories 
                        SET value = ?, raw_text = ?, confidence = ?, update_count = update_count + 1, updated_at = ?
                        WHERE memory_id = ?
                    """, (clean_val, raw_text or clean_val, confidence, now_iso, mem_id))
                    action = "updated"
                else:
                    # Mismo valor: incrementar confianza y contador de accesos
                    cursor.execute("""
                        UPDATE user_memories 
                        SET access_count = access_count + 1, confidence = MIN(1.0, confidence + 0.05), updated_at = ?
                        WHERE memory_id = ?
                    """, (now_iso, mem_id))
                    action = "reinforced"
            else:
                cursor.execute("""
                    INSERT INTO user_memories 
                    (memory_id, user_id, category, key, value, raw_text, confidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (mem_id, user_id, category, clean_key, clean_val, raw_text or clean_val, confidence, now_iso, now_iso))
                action = "created"

            conn.commit()

        return {
            "action": action,
            "memory_id": mem_id,
            "user_id": user_id,
            "category": category,
            "key": clean_key,
            "value": clean_val,
            "confidence": confidence
        }

    def _derive_key_from_value(self, val: str) -> str:
        # Extraer las primeras palabras representativas como clave
        tokens = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", val.lower())
        if tokens:
            return "_".join(tokens[:3])
        return "general_fact"

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_memories WHERE memory_id = ? AND is_active = 1", (memory_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all(
        self,
        user_id: str = "default_user",
        category: Optional[str] = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM user_memories WHERE user_id = ?"
            params: List[Any] = [user_id]

            if category:
                query += " AND category = ?"
                params.append(category)
            if active_only:
                query += " AND is_active = 1"

            query += " ORDER BY updated_at DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def search(
        self,
        query: str,
        user_id: str = "default_user",
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Búsqueda contextual de hechos y preferencias por coincidencia léxica / semántica en claves y texto.
        """
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", query.lower())
        all_memories = self.get_all(user_id=user_id, category=category, active_only=True)
        if not tokens or not all_memories:
            return all_memories[:limit]

        scored: List[tuple[float, Dict[str, Any]]] = []
        for mem in all_memories:
            haystack = f"{mem['key']} {mem['value']} {mem['raw_text'] or ''} {mem['category']}".lower()
            matches = sum(1 for t in tokens if t in haystack)
            if matches > 0:
                score = (matches / len(tokens)) * mem["confidence"]
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def update(self, memory_id: str, new_value: str, confidence: Optional[float] = None) -> bool:
        clean_val = new_value.strip()
        now_iso = datetime.now().isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value, user_id FROM user_memories WHERE memory_id = ? AND is_active = 1", (memory_id,))
            row = cursor.fetchone()
            if not row:
                return False

            old_val = row["value"]
            u_id = row["user_id"]
            cursor.execute("""
                INSERT INTO user_memory_history (memory_id, user_id, old_value, new_value, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (memory_id, u_id, old_val, clean_val, "manual_update"))

            if confidence is not None:
                cursor.execute("""
                    UPDATE user_memories 
                    SET value = ?, confidence = ?, update_count = update_count + 1, updated_at = ?
                    WHERE memory_id = ?
                """, (clean_val, confidence, now_iso, memory_id))
            else:
                cursor.execute("""
                    UPDATE user_memories 
                    SET value = ?, update_count = update_count + 1, updated_at = ?
                    WHERE memory_id = ?
                """, (clean_val, now_iso, memory_id))

            conn.commit()
            return True

    def delete(self, memory_id: str, soft_delete: bool = True) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if soft_delete:
                cursor.execute("UPDATE user_memories SET is_active = 0, updated_at = ? WHERE memory_id = ?", 
                               (datetime.now().isoformat(), memory_id))
            else:
                cursor.execute("DELETE FROM user_memories WHERE memory_id = ?", (memory_id,))
            affected = cursor.rowcount > 0
            conn.commit()
            return affected

    def extract_and_add_from_text(self, text: str, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """
        Extracción heurística de preferencias y directivas a partir del diálogo del usuario.
        Inspirado en el pipeline extractivo de Mem0.
        """
        extracted = []
        patterns = [
            (r"(?:prefiero|me gusta|mi preferencia es|prioriza)\s+([^\.\n]+)", UserMemoryCategory.PREFERENCE.value, "preferencia"),
            (r"(?:siempre usa|usa siempre|debes usar|utiliza)\s+([^\.\n]+)", UserMemoryCategory.WORKFLOW_RULE.value, "regla_uso"),
            (r"(?:no uses|nunca hagas|evita|no me gusta|prohibido)\s+([^\.\n]+)", UserMemoryCategory.SYSTEM_DIRECTIVE.value, "restriccion"),
            (r"(?:trabajo de|mi horario es|mis turnos son)\s+([^\.\n]+)", UserMemoryCategory.PROJECT_CONTEXT.value, "horario_trabajo"),
            (r"(?:mi lenguaje favorito es|programo en)\s+([^\.\n]+)", UserMemoryCategory.PREFERENCE.value, "lenguaje_favorito"),
            (r"(?:responde siempre en|quiero que respondas en)\s+([^\.\n]+)", UserMemoryCategory.PREFERENCE.value, "idioma_respuesta")
        ]

        for pat, cat, key_prefix in patterns:
            matches = re.finditer(pat, text, re.IGNORECASE)
            for m in matches:
                val = m.group(1).strip()
                if len(val) > 2:
                    sub_key = f"{key_prefix}_{len(extracted) + 1}"
                    res = self.add(value=val, category=cat, key=sub_key, user_id=user_id, raw_text=m.group(0))
                    extracted.append(res)
        return extracted

    def get_user_profile_context(self, user_id: str = "default_user") -> str:
        """
        Construye el bloque de contexto de preferencias y perfil de usuario
        para inyección en el prompt del sistema del agente.
        """
        memories = self.get_all(user_id=user_id, active_only=True)
        if not memories:
            return ""

        lines = ["[MEMORIA DE USUARIO Y PREFERENCIAS PERSISTENTES (Mem0 Layer)]:"]
        for mem in memories:
            lines.append(f"- [{mem['category']}] {mem['key']}: {mem['value']} (confianza: {mem['confidence']:.2f})")
        return "\n".join(lines)
