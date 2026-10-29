"""
Planificador de Tareas en Segundo Plano y Demonio de Latido Autónomo (Heartbeat Daemon) para JEV.
Permite al agente ejecutar tareas periódicas o programadas en segundo plano
(e.g., monitoreo de carpetas, mantenimiento, recordatorios y comprobaciones de estado).
"""
from typing import Dict, Any, List, Optional, Callable
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult


@dataclass
class ScheduledJob:
    """Representa una tarea programada en el planificador autónomo."""
    job_id: str
    name: str
    action_type: str  # 'command', 'python', 'callback'
    payload: str
    interval_seconds: float
    recurring: bool = False
    next_run: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    runs_count: int = 0
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutonomousScheduler:
    """Demonio de segundo plano que ejecuta tareas programadas sin bloquear el hilo principal."""

    _instance: Optional['AutonomousScheduler'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, check_interval: float = 1.0):
        if self._initialized:
            return
        self._initialized = True
        self.check_interval = check_interval
        self.jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.Lock()
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia el demonio de latido en segundo plano."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="JEV-HeartbeatDaemon")
        self._thread.start()

    def stop(self) -> None:
        """Detiene el demonio de latido."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def add_job(
        self,
        name: str,
        action_type: str,
        payload: str,
        delay_seconds: float,
        recurring: bool = False,
        callback: Optional[Callable[[ScheduledJob], None]] = None
    ) -> str:
        """Programa una nueva tarea y devuelve su identificador único."""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = ScheduledJob(
            job_id=job_id,
            name=name,
            action_type=action_type,
            payload=payload,
            interval_seconds=delay_seconds,
            recurring=recurring,
            next_run=time.time() + delay_seconds
        )
        if callback:
            job.metadata["callback"] = callback

        with self._lock:
            self.jobs[job_id] = job

        # Iniciar el daemon si no estaba corriendo
        if not self.running:
            self.start()

        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """Cancela y desactiva una tarea programada."""
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].active = False
                del self.jobs[job_id]
                return True
        return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Devuelve la lista de tareas activas."""
        with self._lock:
            now = time.time()
            return [
                {
                    "job_id": j.job_id,
                    "name": j.name,
                    "action_type": j.action_type,
                    "payload": j.payload,
                    "recurring": j.recurring,
                    "interval_seconds": j.interval_seconds,
                    "seconds_until_next_run": max(0, round(j.next_run - now, 1)),
                    "runs_count": j.runs_count
                }
                for j in self.jobs.values() if j.active
            ]

    def _heartbeat_loop(self) -> None:
        """Bucle continuo del demonio de latido."""
        while self.running:
            now = time.time()
            jobs_to_run = []
            with self._lock:
                for j in list(self.jobs.values()):
                    if j.active and now >= j.next_run:
                        jobs_to_run.append(j)
                        if j.recurring:
                            j.next_run = now + j.interval_seconds
                        else:
                            j.active = False
                            del self.jobs[j.job_id]

            for job in jobs_to_run:
                self._execute_job(job)

            time.sleep(self.check_interval)

    def _execute_job(self, job: ScheduledJob) -> None:
        """Ejecuta una tarea programada en un hilo independiente para no retrasar el bucle."""
        def run_target():
            job.last_run = time.time()
            job.runs_count += 1
            cb = job.metadata.get("callback")
            if cb and callable(cb):
                try:
                    cb(job)
                except Exception as e:
                    print(f"[HeartbeatDaemon] Error en callback de job {job.job_id}: {e}")

        t = threading.Thread(target=run_target, daemon=True)
        t.start()


# -------------------------------------------------------------
# HERRAMIENTAS REGISTRABLES EN EL TOOL REGISTRY
# -------------------------------------------------------------

class ScheduleTaskTool(BaseTool):
    """Permite al agente programar tareas autónomas para ejecutarse en el futuro o periódicamente."""
    name = "schedule_task"
    description = (
        "Programa una tarea o recordatorio en segundo plano para ejecutarse tras cierto tiempo "
        "o periódicamente cada N segundos sin bloquear la sesión actual."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nombre o descripción de la tarea programada."},
            "delay_seconds": {"type": "integer", "description": "Segundos a esperar antes de la ejecución."},
            "recurring": {"type": "boolean", "description": "Si es True, la tarea se repetirá indefinidamente cada delay_seconds."},
            "action_type": {"type": "string", "enum": ["command", "reminder", "script"], "description": "Tipo de acción."},
            "payload": {"type": "string", "description": "Comando, mensaje o código a ejecutar."}
        },
        "required": ["name", "delay_seconds", "payload"]
    }

    def __init__(self, scheduler: Optional[AutonomousScheduler] = None):
        self.scheduler = scheduler or AutonomousScheduler()

    def execute(self, name: str, delay_seconds: int, payload: str, recurring: bool = False, action_type: str = "reminder", **kwargs) -> ToolResult:
        try:
            job_id = self.scheduler.add_job(
                name=name,
                action_type=action_type,
                payload=payload,
                delay_seconds=float(delay_seconds),
                recurring=recurring
            )
            return ToolResult(
                success=True,
                output=f"Tarea '{name}' programada exitosamente con ID '{job_id}' (Se ejecutará en {delay_seconds}s{' de forma recurrente' if recurring else ''}).",
                data={"job_id": job_id, "name": name, "delay_seconds": delay_seconds, "recurring": recurring}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Fallo al programar tarea: {str(e)}")


class ListScheduledTasksTool(BaseTool):
    """Lista todas las tareas programadas activas en el demonio."""
    name = "list_scheduled_tasks"
    description = "Muestra todas las tareas programadas actualmente activas en segundo plano."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, scheduler: Optional[AutonomousScheduler] = None):
        self.scheduler = scheduler or AutonomousScheduler()

    def execute(self, **kwargs) -> ToolResult:
        jobs = self.scheduler.list_jobs()
        return ToolResult(
            success=True,
            output=f"Tareas programadas activas: {len(jobs)}.\n" + ("\n".join(f"- [{j['job_id']}] {j['name']} (restan {j['seconds_until_next_run']}s)" for j in jobs) if jobs else "(Ninguna tarea pendiente)"),
            data={"jobs": jobs}
        )
