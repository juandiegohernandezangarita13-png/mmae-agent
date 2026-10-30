"""
Motor de Aprendizaje en Segundo Plano y Evolución Adaptativa (Inspirado en LangMem y Leta).
Ejecuta la extracción asíncrona de puntos clave y hechos conversacionales sin bloquear
el turno principal del agente, y ajusta progresivamente el perfil del usuario y los hábitos
operativos a lo largo del tiempo.
"""
import re
import queue
import threading
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from core.memory.user_memory import UserPersistentMemory, UserMemoryCategory
from core.memory.temporal_graph import TemporalKnowledgeGraph


class BackgroundMemoryWorker:
    """
    Trabajador en segundo plano (LangMem Worker) y Motor de Evolución Continua (Leta Engine):
    - Cola no bloqueante para ingesta de turnos conversacionales.
    - Extractor de hechos semánticos, directivas y relaciones temporales.
    - Perfilador progresivo del usuario (estilo de respuesta, horarios, nivel de detalle).
    - Registro de evolución histórica y métricas de adaptación.
    """

    def __init__(
        self,
        user_memory: UserPersistentMemory,
        temporal_graph: TemporalKnowledgeGraph,
        profile_path: Optional[Path] = None,
        poll_interval: float = 0.5
    ):
        self.user_memory = user_memory
        self.temporal_graph = temporal_graph
        self.profile_path = profile_path or (Path("data/memory") / "adaptive_profile.json")
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.poll_interval = poll_interval

        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.profile_data = self._load_profile()

    def _load_profile(self) -> Dict[str, Any]:
        if self.profile_path.exists():
            try:
                return json.loads(self.profile_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "total_turns": 0,
            "user_verbosity_preference": "concise",
            "detected_language": "es",
            "active_hours": {},
            "preferred_tools": {},
            "task_success_rate": 1.0,
            "last_active": datetime.now().isoformat()
        }

    def _save_profile(self) -> None:
        try:
            self.profile_path.write_text(
                json.dumps(self.profile_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def enqueue_turn(
        self,
        user_input: str,
        agent_output: str,
        tools_used: Optional[List[str]] = None,
        task_success: bool = True,
        user_id: str = "default_user"
    ) -> None:
        """Encola un turno conversacional para análisis en segundo plano (no bloqueante)."""
        turn_data = {
            "user_input": user_input,
            "agent_output": agent_output,
            "tools_used": tools_used or [],
            "task_success": task_success,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        self._queue.put(turn_data)

    def start(self) -> None:
        """Inicia el hilo trabajador en segundo plano."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="BackgroundMemoryWorker")
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Detiene de forma limpia el hilo trabajador."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                turn = self._queue.get(timeout=self.poll_interval)
                self._distill_and_learn(turn)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def process_pending(self, sync: bool = True) -> int:
        """Procesa todas las tareas pendientes en la cola (útil para pruebas o flush síncrono)."""
        count = 0
        while not self._queue.empty():
            try:
                turn = self._queue.get_nowait()
                self._distill_and_learn(turn)
                self._queue.task_done()
                count += 1
            except queue.Empty:
                break
        return count

    def _distill_and_learn(self, turn: Dict[str, Any]) -> None:
        """
        Núcleo de destilación LangMem + adaptación continua Leta:
        1. Extrae hechos y preferencias explícitas del usuario hacia Mem0.
        2. Detecta declaraciones temporales hacia el TKG de Graffiti.
        3. Actualiza el perfil adaptativo del usuario.
        """
        user_text = turn["user_input"]
        agent_text = turn["agent_output"]
        user_id = turn.get("user_id", "default_user")

        # 1. Extracción hacia Mem0
        self.user_memory.extract_and_add_from_text(user_text, user_id=user_id)

        # 2. Extracción de Hechos Temporales (Graffiti)
        self._extract_temporal_facts(user_text)

        # 3. Evolución Adaptativa (Leta)
        with self._lock:
            self.profile_data["total_turns"] += 1
            self.profile_data["last_active"] = turn["timestamp"]

            # Registro de horario
            hour_str = str(datetime.now().hour)
            self.profile_data["active_hours"][hour_str] = self.profile_data["active_hours"].get(hour_str, 0) + 1

            # Detección de herramientas preferidas
            for tool in turn.get("tools_used", []):
                self.profile_data["preferred_tools"][tool] = self.profile_data["preferred_tools"].get(tool, 0) + 1

            # Longitud preferida
            if len(user_text.split()) < 15 and "resumen" in user_text.lower():
                self.profile_data["user_verbosity_preference"] = "concise"
            elif len(user_text.split()) > 40:
                self.profile_data["user_verbosity_preference"] = "detailed"

            self._save_profile()

    def _extract_temporal_facts(self, text: str) -> None:
        """Detecta afirmaciones temporales de transición o estado actual."""
        temporal_patterns = [
            (r"(?:soy|me llamo|mi nombre es)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ]+)", "has_name"),
            # "ahora uso X" / "ahora trabajo en X" / "cambié a X"
            (r"(?:ahora uso|cambié a|me pasé a|migré a)\s+([a-zA-Z0-9_\-\.\+]+)", "uses_tool"),
            (r"(?:ahora trabajo en|nuevo proyecto es|estoy desarrollando)\s+([a-zA-Z0-9_\-\.\+]+)", "active_project"),
            (r"(?:mi sistema operativo es|uso)\s+(windows|linux|macos|ubuntu)", "operates_on")
        ]

        for pat, rel in temporal_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                target = m.group(1).strip()
                self.temporal_graph.add_relation(
                    source="User",
                    relation=rel,
                    target=target,
                    is_functional=True,
                    evidence=f"Extraído de: {m.group(0)}"
                )

    def get_evolution_metrics(self) -> Dict[str, Any]:
        """Devuelve el estado evolutivo del agente."""
        with self._lock:
            return dict(self.profile_data)

    def get_adaptive_context_summary(self) -> str:
        """Construye un resumen adaptativo para inyectar en el agente."""
        p = self.get_evolution_metrics()
        lines = [
            f"[PERFIL ADAPTATIVO CONTINUO (Leta Layer)]:",
            f"- Turnos interactuados: {p.get('total_turns', 0)}",
            f"- Preferencia de concisión: {p.get('user_verbosity_preference', 'concise')}",
            f"- Idioma primario detectado: {p.get('detected_language', 'es')}"
        ]
        if p.get("preferred_tools"):
            top_tools = sorted(p["preferred_tools"].items(), key=lambda x: x[1], reverse=True)[:3]
            tool_str = ", ".join(f"{t} ({cnt})" for t, cnt in top_tools)
            lines.append(f"- Herramientas más frecuentes: {tool_str}")

        return "\n".join(lines)
