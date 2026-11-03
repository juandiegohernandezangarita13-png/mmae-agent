"""
Módulo de Gestión de Memoria Procedimental y Decaimiento Cognitivo Temporal en SQLite.
Gestiona el ciclo de vida de los procedimientos aprendidos, su índice de confianza (confidence_score)
y su decaimiento matemático cuando no han sido verificados durante más de 7 días.
"""
from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import BASE_DIR, MEMORY_DIR
from utils.logger import log

DEFAULT_DB_PATH = MEMORY_DIR / "knowledge_base.db"


@dataclass
class ProceduralRecord:
    """Representación fuertemente tipada de un procedimiento en SQLite."""
    id: int
    category: str
    phase: str
    trigger_keywords: str
    problem_description: str
    solution_summary: str
    working_snippet: str
    times_reused: int
    last_used: str
    confidence_score: float
    last_verified_at: Optional[str]
    success_count: int
    failure_count: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProceduralRecord:
        return cls(
            id=row["id"],
            category=row["category"] or "general",
            phase=row["phase"] if "phase" in row.keys() else "general",
            trigger_keywords=row["trigger_keywords"] or "",
            problem_description=row["problem_description"] or "",
            solution_summary=row["solution_summary"] or "",
            working_snippet=row["working_snippet"] or "",
            times_reused=row["times_reused"] or 0,
            last_used=str(row["last_used"] or ""),
            confidence_score=float(row["confidence_score"] if row["confidence_score"] is not None else 1.0),
            last_verified_at=str(row["last_verified_at"]) if row["last_verified_at"] else None,
            success_count=int(row["success_count"] or 0),
            failure_count=int(row["failure_count"] or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "phase": self.phase,
            "trigger_keywords": self.trigger_keywords,
            "problem_description": self.problem_description,
            "solution_summary": self.solution_summary,
            "working_snippet": self.working_snippet,
            "times_reused": self.times_reused,
            "last_used": self.last_used,
            "confidence_score": round(self.confidence_score, 4),
            "last_verified_at": self.last_verified_at,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }


class ProceduralMemoryManager:
    """
    Controlador de la tabla procedural_solutions con soporte para decaimiento cognitivo
    y actualización determinista de confiabilidad.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        """Asegura la existencia de la tabla y las columnas requeridas para el decaimiento temporal."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS procedural_solutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    phase TEXT DEFAULT 'general',
                    trigger_keywords TEXT,
                    problem_description TEXT,
                    solution_summary TEXT,
                    working_snippet TEXT,
                    times_reused INTEGER DEFAULT 1,
                    last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                    confidence_score REAL DEFAULT 1.0,
                    last_verified_at DATETIME,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0
                )
            """)

            # Migración aditiva y segura para bases de datos existentes
            cursor.execute("PRAGMA table_info(procedural_solutions)")
            existing_columns = {col[1] for col in cursor.fetchall()}

            migrations = [
                ("confidence_score", "REAL DEFAULT 1.0"),
                ("last_verified_at", "DATETIME"),
                ("success_count", "INTEGER DEFAULT 0"),
                ("failure_count", "INTEGER DEFAULT 0"),
                ("phase", "TEXT DEFAULT 'general'"),
            ]

            for col_name, col_def in migrations:
                if col_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE procedural_solutions ADD COLUMN {col_name} {col_def}")
                        log.info(f"Columna '{col_name}' añadida con éxito a procedural_solutions.")
                    except sqlite3.OperationalError:
                        pass
            conn.commit()

    def apply_temporal_decay(
        self,
        decay_threshold_days: float = 7.0,
        half_life_days: float = 14.0,
        min_confidence: float = 0.05,
    ) -> int:
        """
        Aplica decaimiento cognitivo temporal a todos los procedimientos que lleven más
        de `decay_threshold_days` (7 días) sin haber sido verificados.
        Usa decaimiento exponencial basado en vida media (half-life):
            factor = (0.5) ** (días_exceso / half_life_days)
        """
        now = datetime.now(timezone.utc)
        updated_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, confidence_score, last_verified_at, last_used FROM procedural_solutions")
            rows = cursor.fetchall()

            for row in rows:
                p_id = row["id"]
                current_score = float(row["confidence_score"] if row["confidence_score"] is not None else 1.0)
                
                # Determinar fecha base de referencia
                ref_time_str = row["last_verified_at"] or row["last_used"]
                if not ref_time_str:
                    continue

                ref_time: Optional[datetime] = None
                # Intentar parsear ISO con o sin 'Z' / offset
                clean_time_str = str(ref_time_str).replace("Z", "+00:00")
                for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
                    try:
                        ref_time = datetime.strptime(clean_time_str, fmt)
                        break
                    except ValueError:
                        continue

                if not ref_time:
                    try:
                        ref_time = datetime.fromisoformat(clean_time_str)
                    except Exception:
                        continue

                if ref_time.tzinfo is None:
                    ref_time = ref_time.replace(tzinfo=timezone.utc)

                elapsed_seconds = (now - ref_time).total_seconds()
                elapsed_days = max(0.0, elapsed_seconds / 86400.0)

                if elapsed_days > decay_threshold_days:
                    excess_days = elapsed_days - decay_threshold_days
                    # Decaimiento exponencial controlado
                    decay_factor = math.pow(0.5, excess_days / half_life_days)
                    new_score = max(min_confidence, current_score * decay_factor)
                    new_score = round(new_score, 4)

                    if abs(new_score - current_score) > 0.0001:
                        cursor.execute(
                            "UPDATE procedural_solutions SET confidence_score = ? WHERE id = ?",
                            (new_score, p_id),
                        )
                        updated_count += 1

            conn.commit()

        if updated_count > 0:
            log.info(f"🕒 [Chronos Decaimiento]: {updated_count} procedimiento(s) actualizados por inactividad > {decay_threshold_days}d.")
        return updated_count

    def record_verification(self, procedure_id: int, success: bool) -> float:
        """
        Registra el resultado de una prueba determinista (éxito o fallo) sobre un procedimiento,
        actualiza contadores, `last_verified_at` y recalcula el `confidence_score` (Laplace Smoothing).
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT success_count, failure_count FROM procedural_solutions WHERE id = ?",
                (procedure_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Procedimiento con ID {procedure_id} no existe.")

            s_count = int(row["success_count"] or 0)
            f_count = int(row["failure_count"] or 0)

            if success:
                s_count += 1
            else:
                f_count += 1

            # Suavizado de Laplace: (éxitos + 1) / (total + 2) para evitar 0.0 o 1.0 absoluto
            new_confidence = round((s_count + 1.0) / (s_count + f_count + 2.0), 4)

            cursor.execute("""
                UPDATE procedural_solutions
                SET success_count = ?,
                    failure_count = ?,
                    confidence_score = ?,
                    last_verified_at = ?
                WHERE id = ?
            """, (s_count, f_count, new_confidence, now_iso, procedure_id))
            conn.commit()

        log.info(
            f"✅ [Verificación Procedimiento {procedure_id}]: Éxito={success} | "
            f"Nuevo Confidence={new_confidence} (Éxitos: {s_count}, Fallos: {f_count})"
        )
        return new_confidence

    def get_lowest_confidence_procedures(self, limit: int = 1) -> List[ProceduralRecord]:
        """
        Retorna los procedimientos con menor puntaje de confianza o más antiguos sin verificar,
        para alimentar el bucle de curiosidad autónomo.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM procedural_solutions
                ORDER BY confidence_score ASC,
                         COALESCE(last_verified_at, '1970-01-01') ASC,
                         id ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [ProceduralRecord.from_row(r) for r in rows]

    def upsert_procedure(
        self,
        category: str,
        trigger_keywords: str,
        problem_description: str,
        solution_summary: str,
        working_snippet: str,
        phase: str = "general",
        confidence_score: float = 1.0,
    ) -> int:
        """Crea o actualiza una solución procedimental."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO procedural_solutions 
                (category, phase, trigger_keywords, problem_description, solution_summary, 
                 working_snippet, confidence_score, last_verified_at, success_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
            """, (
                category,
                phase,
                trigger_keywords,
                problem_description,
                solution_summary,
                working_snippet,
                confidence_score,
                now_iso,
            ))
            conn.commit()
            return cursor.lastrowid or 0


__all__ = ["ProceduralRecord", "ProceduralMemoryManager", "DEFAULT_DB_PATH"]
