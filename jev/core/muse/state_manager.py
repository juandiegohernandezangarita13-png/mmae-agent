"""
Gestor de Estado Persistente (MuseStateManager) con motor SQLite.
Almacena y coordina el ciclo de vida de tareas largas, pasos del plan,
hipótesis de corrección ante fallos e historial del canal de intención (Commentary Channel).
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import sqlite3
import json
import time
import uuid
import logging

from jev.config import BASE_DIR

logger = logging.getLogger("jev.muse.state_manager")

DEFAULT_DB_PATH = BASE_DIR / "data" / "memory" / "muse_spark_state.db"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


@dataclass
class PlanStep:
    step_index: int
    title: str
    description: str
    status: StepStatus = StepStatus.PENDING
    retry_count: int = 0
    hypothesis: Optional[str] = None
    result_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "hypothesis": self.hypothesis,
            "result_summary": self.result_summary
        }


@dataclass
class TurnRecord:
    turn_index: int
    step_index: int
    thought: str
    intent: str
    action: str
    params: Dict[str, Any]
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    duration: float = 0.0
    timestamp: float = field(default_factory=time.time)


class MuseStateManager:
    """
    Gestor de persistencia SQLite para el bucle de ejecución de Muse Spark.
    Garantiza resiliencia a reinicios y trazabilidad de cada pensamiento, intención y acción.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """Crea las tablas relacionales para tareas, pasos de plan y turnos."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS muse_tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS muse_plan_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    hypothesis TEXT,
                    result_summary TEXT,
                    FOREIGN KEY (task_id) REFERENCES muse_tasks(id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS muse_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    turn_index INTEGER NOT NULL,
                    thought TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    output TEXT,
                    error TEXT,
                    exit_code INTEGER,
                    duration REAL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES muse_tasks(id)
                )
            """)

    def create_task(self, goal: str, steps: List[PlanStep]) -> str:
        """Crea una nueva tarea larga y persiste sus pasos planificados iniciales."""
        task_id = str(uuid.uuid4())
        now = time.time()

        with self.conn:
            self.conn.execute(
                "INSERT INTO muse_tasks (id, goal, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, goal, TaskStatus.RUNNING.value, now, now)
            )
            for step in steps:
                self.conn.execute(
                    """
                    INSERT INTO muse_plan_steps 
                    (task_id, step_index, title, description, status, retry_count, hypothesis, result_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        step.step_index,
                        step.title,
                        step.description,
                        step.status.value,
                        step.retry_count,
                        step.hypothesis,
                        step.result_summary
                    )
                )
        logger.info(f"Tarea Muse '{task_id}' creada con {len(steps)} pasos.")
        return task_id

    def get_plan_steps(self, task_id: str) -> List[PlanStep]:
        """Recupera la lista ordenada de pasos de una tarea."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT step_index, title, description, status, retry_count, hypothesis, result_summary "
            "FROM muse_plan_steps WHERE task_id = ? ORDER BY step_index ASC",
            (task_id,)
        )
        rows = cursor.fetchall()
        return [
            PlanStep(
                step_index=r["step_index"],
                title=r["title"],
                description=r["description"],
                status=StepStatus(r["status"]),
                retry_count=r["retry_count"],
                hypothesis=r["hypothesis"],
                result_summary=r["result_summary"]
            )
            for r in rows
        ]

    def get_active_step(self, task_id: str) -> Optional[PlanStep]:
        """Obtiene el primer paso que esté IN_PROGRESS o PENDING."""
        steps = self.get_plan_steps(task_id)
        for s in steps:
            if s.status in (StepStatus.IN_PROGRESS, StepStatus.PENDING):
                return s
        return None

    def mark_step_in_progress(self, task_id: str, step_index: int) -> None:
        """Transiciona un paso a estado IN_PROGRESS."""
        with self.conn:
            self.conn.execute(
                "UPDATE muse_plan_steps SET status = ? WHERE task_id = ? AND step_index = ?",
                (StepStatus.IN_PROGRESS.value, task_id, step_index)
            )
            self._touch_task(task_id)

    def mark_step_completed(self, task_id: str, step_index: int, summary: str = "") -> None:
        """Marca un paso como COMPLETED y guarda su resultado."""
        with self.conn:
            self.conn.execute(
                "UPDATE muse_plan_steps SET status = ?, result_summary = ? WHERE task_id = ? AND step_index = ?",
                (StepStatus.COMPLETED.value, summary, task_id, step_index)
            )
            self._touch_task(task_id)
        logger.info(f"Paso {step_index} de tarea '{task_id}' completado exitosamente.")

    def record_step_failure(
        self,
        task_id: str,
        step_index: int,
        error: str,
        hypothesis: Optional[str] = None,
        mark_failed: bool = False
    ) -> int:
        """
        Registra un fallo en el paso, incrementa su contador de reintentos
        y guarda la hipótesis de corrección formulada por el agente.
        """
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT retry_count FROM muse_plan_steps WHERE task_id = ? AND step_index = ?",
                (task_id, step_index)
            )
            row = cursor.fetchone()
            current_retries = (row["retry_count"] if row else 0) + 1
            new_status = StepStatus.FAILED.value if mark_failed else StepStatus.IN_PROGRESS.value

            self.conn.execute(
                """
                UPDATE muse_plan_steps 
                SET retry_count = ?, hypothesis = ?, status = ?
                WHERE task_id = ? AND step_index = ?
                """,
                (current_retries, hypothesis or error, new_status, task_id, step_index)
            )
            self._touch_task(task_id)
        return current_retries

    def record_turn(self, task_id: str, turn: TurnRecord) -> None:
        """Persiste una interacción completa del canal de pensamiento/intención y su ejecución."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO muse_turns
                (task_id, step_index, turn_index, thought, intent, action, params, success, output, error, exit_code, duration, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    turn.step_index,
                    turn.turn_index,
                    turn.thought,
                    turn.intent,
                    turn.action,
                    json.dumps(turn.params),
                    1 if turn.success else 0,
                    turn.output,
                    turn.error,
                    turn.exit_code,
                    turn.duration,
                    turn.timestamp
                )
            )
            self._touch_task(task_id)

    def get_recent_turns(self, task_id: str, limit: int = 5) -> List[TurnRecord]:
        """Obtiene los últimos N turnos ejecutados para mantener contexto fresco."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT step_index, turn_index, thought, intent, action, params, success, output, error, exit_code, duration, timestamp
            FROM muse_turns WHERE task_id = ? ORDER BY turn_index DESC LIMIT ?
            """,
            (task_id, limit)
        )
        rows = cursor.fetchall()
        turns = []
        for r in reversed(rows):
            try:
                parsed_params = json.loads(r["params"])
            except Exception:
                parsed_params = {}
            turns.append(TurnRecord(
                turn_index=r["turn_index"],
                step_index=r["step_index"],
                thought=r["thought"],
                intent=r["intent"],
                action=r["action"],
                params=parsed_params,
                success=bool(r["success"]),
                output=r["output"] or "",
                error=r["error"],
                exit_code=r["exit_code"] or 0,
                duration=r["duration"] or 0.0,
                timestamp=r["timestamp"]
            ))
        return turns

    def set_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Actualiza el estado general de la tarea (COMPLETED, FAILED, etc.)."""
        with self.conn:
            self.conn.execute(
                "UPDATE muse_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, time.time(), task_id)
            )

    def get_plan_summary_text(self, task_id: str) -> str:
        """Genera una vista textual del estado actual del plan para el prompt del LLM."""
        steps = self.get_plan_steps(task_id)
        if not steps:
            return "(No hay pasos de plan registrados)"

        lines = []
        for s in steps:
            icon = "⏳"
            if s.status == StepStatus.IN_PROGRESS:
                icon = "▶️ [ACTUAL]"
            elif s.status == StepStatus.COMPLETED:
                icon = "✅ [COMPLETO]"
            elif s.status == StepStatus.FAILED:
                icon = "❌ [FALLIDO]"

            detail = f"Paso {s.step_index}: {s.title} ({icon})"
            if s.status == StepStatus.COMPLETED and s.result_summary:
                detail += f" -> {s.result_summary}"
            elif s.status == StepStatus.IN_PROGRESS and s.retry_count > 0 and s.hypothesis:
                detail += f" -> [Reintento {s.retry_count}] Hipótesis previa: {s.hypothesis}"
            lines.append(detail)

        return "\n".join(lines)

    def _touch_task(self, task_id: str) -> None:
        """Actualiza la marca temporal de modificación de una tarea."""
        self.conn.execute(
            "UPDATE muse_tasks SET updated_at = ? WHERE id = ?",
            (time.time(), task_id)
        )

    def close(self) -> None:
        """Cierra la conexión con la base de datos."""
        try:
            self.conn.close()
        except Exception:
            pass
