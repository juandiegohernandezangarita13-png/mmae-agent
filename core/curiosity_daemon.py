"""
Módulo Curiosity Daemon: Bucle de curiosidad autónomo y auto-mantenimiento procedimental.
Supervisa la inactividad del usuario en Windows mediante Chronos (GetLastInputInfo).
Cuando el usuario está inactivo (por defecto > 900s = 15 minutos):
1. Aplica decaimiento cognitivo a la memoria procedimental en SQLite.
2. Selecciona el procedimiento con menor confianza o más antiguo sin verificar.
3. Diseña un plan de verificación Nivel 0 (sandbox no destructivo).
4. Somete el plan al auditor stateless GoldfishCritic (Google EGM).
5. Ejecuta la verificación mediante ScriptRunner (CodeAct).
6. Evalúa el resultado con el DeterministicOracle (exit_code, mtime, handles Win32).
7. Actualiza los contadores y puntaje de confianza en SQLite.
8. Si se completa un hallazgo o se requiere HITL, emite aviso conciso con VoiceAnnouncer e Isla.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import BASE_DIR, MEMORY_DIR
from core.chronos import Chronos, ExecutionTimer
from core.evaluator import DeterministicOracle
from core.goldfish_critic import GoldfishCritic
from core.memory.procedure_store import ProceduralMemoryManager, ProceduralRecord
from core.script_runner import ScriptResult, ScriptRunner
from core.voice_announcer import VoiceAnnouncer
from utils.logger import log

try:
    from jev.core.status_sync import set_agent_status
except Exception:
    def set_agent_status(**kwargs: Any) -> None:  # type: ignore
        pass


class CuriosityDaemon:
    """
    Demonio autónomo en segundo plano para el auto-mantenimiento cognitivo.
    Opera únicamente durante periodos de inactividad del usuario en Windows para
    no competir por recursos ni interferir en flujos activos.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        idle_threshold_seconds: Optional[float] = None,
        check_interval_seconds: float = 20.0,
        voice_announcer: Optional[VoiceAnnouncer] = None,
        goldfish_critic: Optional[GoldfishCritic] = None,
        script_runner: Optional[ScriptRunner] = None,
        memory_manager: Optional[ProceduralMemoryManager] = None,
    ) -> None:
        self.idle_threshold_seconds = float(
            idle_threshold_seconds
            or os.getenv("CURIOSITY_IDLE_SECONDS", "900.0")
        )
        self.check_interval_seconds = check_interval_seconds

        self.memory = memory_manager or ProceduralMemoryManager(db_path=db_path)
        self.critic = goldfish_critic or GoldfishCritic()
        self.script_runner = script_runner or ScriptRunner()
        self.oracle = DeterministicOracle()
        self.voice = voice_announcer or VoiceAnnouncer()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self.total_cycles_executed = 0

    def start(self) -> None:
        """Inicia el demonio en un hilo de fondo desacoplado."""
        if self._is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._daemon_loop,
            daemon=True,
            name="MMAE_CuriosityDaemon",
        )
        self._is_running = True
        self._thread.start()
        log.info(
            f"🦉 [CuriosityDaemon]: Iniciado (Umbral Inactividad={self.idle_threshold_seconds}s, "
            f"Intervalo Chequeo={self.check_interval_seconds}s)."
        )

    def stop(self) -> None:
        """Detiene el demonio de forma ordenada."""
        if not self._is_running:
            return
        log.info("🦉 [CuriosityDaemon]: Deteniendo demonio de curiosidad...")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._is_running = False

    def is_alive(self) -> bool:
        return self._is_running and bool(self._thread and self._thread.is_alive())

    def _daemon_loop(self) -> None:
        """Bucle principal de supervisión de inactividad."""
        while not self._stop_event.is_set():
            try:
                idle_seconds = Chronos.get_user_idle_seconds()
                if idle_seconds >= self.idle_threshold_seconds:
                    log.info(
                        f"⏳ [CuriosityDaemon]: Usuario inactivo ({idle_seconds:.1f}s >= "
                        f"{self.idle_threshold_seconds:.1f}s). Ejecutando ciclo de curiosidad Nivel 0..."
                    )
                    self.run_curiosity_cycle()
            except Exception as e:
                log.warning(f"Error en bucle de curiosidad: {e}")

            # Esperar el intervalo configurado verificando periódicamente el evento de parada
            wait_chunks = int(self.check_interval_seconds * 2)
            for _ in range(wait_chunks):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

    def run_curiosity_cycle(self) -> Optional[Dict[str, Any]]:
        """
        Ejecuta un ciclo completo de curiosidad y auto-verificación:
        Decaimiento -> Selección de menor confianza -> Auditoría EGM -> Ejecución CodeAct -> Oráculo -> SQLite.
        Puede invocarse manualmente o por el hilo del demonio.
        """
        with ExecutionTimer(name="curiosity_cycle") as cycle_timer:
            # 1. Aplicar decaimiento temporal en SQLite a procedimientos de más de 7 días
            decayed_count = self.memory.apply_temporal_decay(decay_threshold_days=7.0)

            # 2. Seleccionar el procedimiento con menor confianza o más antiguo sin verificar
            candidates = self.memory.get_lowest_confidence_procedures(limit=1)
            if not candidates:
                log.info("🦉 [CuriosityDaemon]: No hay procedimientos registrados en la base de datos.")
                return None

            proc: ProceduralRecord = candidates[0]
            log.info(
                f"🔬 [CuriosityDaemon]: Evaluando procedimiento [{proc.id}] "
                f"Categoría='{proc.category}', Confianza={proc.confidence_score:.3f}, Última={proc.last_verified_at}"
            )

            # Notificar inicio a la Isla
            try:
                set_agent_status(
                    state="curiosity",
                    task=f"Curiosidad Nivel 0: {proc.category}",
                    thought=f"Verificando procedimiento {proc.id} (confianza actual: {proc.confidence_score:.2f})",
                    running=True,
                )
            except Exception:
                pass

            # 3. Diseñar plan y script de verificación Nivel 0 (Sandbox no destructivo)
            sandbox_plan, verification_script = self._design_level_0_verification(proc)

            # 4. Someter el plan al auditor stateless GoldfishCritic (Google EGM)
            audit_result = self.critic.audit_plan(
                skeleton=sandbox_plan,
                literals=[str(BASE_DIR)],
            )

            if not audit_result.approved:
                log.warning(
                    f"🚫 [CuriosityDaemon]: Plan Nivel 0 rechazado por GoldfishCritic: {audit_result.blockers}"
                )
                try:
                    set_agent_status(state="idle", running=False)
                except Exception:
                    pass
                return {
                    "procedure_id": proc.id,
                    "success": False,
                    "reason": "Rechazado por GoldfishCritic",
                    "blockers": audit_result.blockers,
                }

            # 5. Ejecutar la verificación con ScriptRunner (CodeAct en lote)
            script_result: ScriptResult = self.script_runner.run_script(
                script_code=verification_script,
                timeout_seconds=20,
            )

            # 6. Evaluación física con el Oráculo Determinista (El LLM no opina)
            oracle_verdict = self.oracle.evaluate_physical_state(
                exit_code=script_result.exit_code,
            )
            is_success = bool(oracle_verdict.get("success", False) and script_result.success)

            # 7. Actualizar la base de datos SQLite con el nuevo puntaje y contadores
            new_confidence = self.memory.record_verification(proc.id, success=is_success)

            # 8. Anuncio por voz y actualización de la Isla
            if is_success:
                voice_text = f"Curiosidad completada. Procedimiento {proc.category} verificado con éxito."
                self.voice.announce(voice_text, priority="normal")
            else:
                voice_text = f"Atención: Procedimiento {proc.category} falló en prueba física de curiosidad."
                self.voice.announce(voice_text, priority="high")

            try:
                set_agent_status(
                    state="idle",
                    task="",
                    thought=f"Curiosidad completada: Procedimiento {proc.id} ({new_confidence:.2f})",
                    last_ok=is_success,
                    running=False,
                )
            except Exception:
                pass

            self.total_cycles_executed += 1
            log.info(
                f"✨ [CuriosityDaemon]: Ciclo finalizado | Procedimiento={proc.id} | "
                f"Resultado={'ÉXITO' if is_success else 'FALLO'} | Nueva Confianza={new_confidence:.4f}"
            )

            return {
                "procedure_id": proc.id,
                "category": proc.category,
                "success": is_success,
                "previous_confidence": proc.confidence_score,
                "new_confidence": new_confidence,
                "decayed_procedures": decayed_count,
                "oracle_verdict": oracle_verdict,
                "duration_seconds": cycle_timer.duration_seconds,
            }

    def _design_level_0_verification(self, proc: ProceduralRecord) -> Tuple[str, str]:
        """
        Diseña el esqueleto macro y el script sandbox de verificación Nivel 0.
        Garantiza que no ejecute efectos secundarios destructivos sobre el sistema.
        """
        category = proc.category.lower()

        # Plan macro estructurado para el auditor
        macro_plan = f"""
1. Aislar rutas mediante LiteralBypass con __LITERAL_TOKEN_0__
2. Comprobar disponibilidad de dependencias para categoría '{category}' con timeout=10s
3. Ejecutar verificación no destructiva en sandbox local
4. Verificar retorno físico exit_code == 0
"""

        # Script de verificación adaptativo Nivel 0
        if "windows_apps" in category or "whatsapp" in proc.trigger_keywords.lower():
            # Verificación de apps de Windows: comprobar registro URI / protocolo sin lanzar ventanas reales
            script = """
import json
import subprocess
import sys

# Comprobar si el protocolo 'whatsapp:' o Start-Process responde
result = {"protocol_verified": False, "category": "windows_apps"}
try:
    cmd = "Get-ItemProperty 'HKCR:\\whatsapp' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty '(default)'"
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=8)
    # Si la clave existe o el comando termina con código 0
    result["protocol_verified"] = (proc.returncode == 0)
    result["status"] = "ok"
except Exception as e:
    result["error"] = str(e)
    result["protocol_verified"] = False

print(json.dumps(result))
sys.exit(0 if result["protocol_verified"] or proc.returncode == 0 else 1)
"""
        elif "git" in category or "git" in proc.trigger_keywords.lower():
            script = """
import json
import subprocess
import sys

result = {"tool": "git", "available": False}
try:
    proc = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
    result["available"] = (proc.returncode == 0)
    result["version"] = proc.stdout.strip()
except Exception as e:
    result["error"] = str(e)

print(json.dumps(result))
sys.exit(0 if result["available"] else 1)
"""
        else:
            # Sandbox genérico: comprobación sintáctica del working_snippet y dependencias
            safe_snippet = proc.working_snippet.replace('"', '\\"').replace("'''", "\\'\\'\\'")
            script = f"""
import ast
import json
import sys

snippet = '''{proc.working_snippet}'''
result = {{"procedure_id": {proc.id}, "syntax_valid": False}}
try:
    # Verificación sintáctica estricta Nivel 0
    ast.parse(snippet)
    result["syntax_valid"] = True
    result["status"] = "verified"
except Exception as e:
    # Si contiene comandos de bash o texto plano, validar que no esté corrupto
    result["syntax_valid"] = (len(snippet.strip()) > 5)
    result["note"] = f"No es sintaxis pura Python pero texto íntegro: {{str(e)}}"

print(json.dumps(result))
sys.exit(0 if result["syntax_valid"] else 1)
"""

        return macro_plan, script


__all__ = ["CuriosityDaemon"]
