"""
Bucle Autónomo de Larga Duración (AgentLoop) inspirado en Muse Spark de Meta.
Implementa:
1. Canal de Intención Previa estricto (Thought/Commentary Channel antes de ejecutar).
2. Planificación por pasos y gestor de estado persistente en SQLite.
3. Validación de estado, formulación de hipótesis ante fallos y auto-corrección.
4. Arnés desacoplado de herramientas con captura de stdout/stderr.
"""
from typing import Dict, Any, Optional, List, Callable
import json
import re
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path

from jev.core.muse.tool_registry import ToolRegistry
from jev.core.muse.execution_engine import ExecutionEngine, ExecutionResult
from jev.core.muse.state_manager import MuseStateManager, PlanStep, StepStatus, TaskStatus, TurnRecord
from jev.core.muse.prompts import MUSE_SPARK_SYSTEM_PROMPT, PLANNING_SYSTEM_PROMPT
from jev.core.llm_client import LocalLLMClient, LLMResponse
from jev.config import default_config

logger = logging.getLogger("jev.muse.agent_loop")


@dataclass
class LoopResult:
    """Resumen de la ejecución del bucle autónomo."""
    task_id: str
    success: bool
    final_output: str
    steps_completed: int
    total_steps: int
    total_turns: int
    duration: float
    history: List[TurnRecord] = field(default_factory=list)


class AgentLoop:
    """
    Bucle cognitivo y de ejecución autónoma Muse Spark para JEV.
    Garantiza que toda acción esté precedida por pensamiento estratégico e intención declarada.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        engine: Optional[ExecutionEngine] = None,
        state_manager: Optional[MuseStateManager] = None,
        llm_client: Optional[LocalLLMClient] = None,
        max_iterations: int = 30,
        max_retries_per_step: int = 3,
        on_thought: Optional[Callable[[str], None]] = None,
        on_intent: Optional[Callable[[str], None]] = None,
        on_action: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_result: Optional[Callable[[ExecutionResult], None]] = None
    ):
        self.registry = registry or ToolRegistry()
        self.engine = engine or ExecutionEngine(registry=self.registry)
        self.state_manager = state_manager or MuseStateManager()
        self.llm_client = llm_client or LocalLLMClient()
        self.max_iterations = max_iterations
        self.max_retries_per_step = max_retries_per_step

        # Callbacks y ganchos de observabilidad en tiempo real
        self.on_thought = on_thought
        self.on_intent = on_intent
        self.on_action = on_action
        self.on_result = on_result

    def run(
        self,
        user_goal: str,
        preplanned_steps: Optional[List[Dict[str, str]]] = None,
        task_id: Optional[str] = None
    ) -> LoopResult:
        """
        Inicia o reanuda el bucle autónomo para resolver una meta de varios pasos.
        """
        start_time = time.time()
        logger.info(f"Iniciando AgentLoop Muse Spark para la meta: '{user_goal}'")

        # 1. Fase de Planificación Inicial
        if task_id:
            tid = task_id
            steps = self.state_manager.get_plan_steps(tid)
        else:
            if preplanned_steps:
                steps = [
                    PlanStep(
                        step_index=idx + 1,
                        title=s.get("title", f"Paso {idx + 1}"),
                        description=s.get("description", "")
                    )
                    for idx, s in enumerate(preplanned_steps)
                ]
            else:
                steps = self._generate_plan(user_goal)
            tid = self.state_manager.create_task(user_goal, steps)

        turn_counter = 0
        last_exec_result: Optional[ExecutionResult] = None
        final_summary = ""

        # 2. Bucle de Ejecución de Tareas Largas
        while turn_counter < self.max_iterations:
            turn_counter += 1

            # Obtener el paso actual en ejecución
            active_step = self.state_manager.get_active_step(tid)
            if not active_step:
                # Todos los pasos han sido completados
                logger.info("Todos los pasos del plan han sido completados.")
                self.state_manager.set_task_status(tid, TaskStatus.COMPLETED)
                final_summary = final_summary or "Plan ejecutado y completado exitosamente."
                break

            # Marcar paso en progreso si estaba pendiente
            if active_step.status == StepStatus.PENDING:
                self.state_manager.mark_step_in_progress(tid, active_step.step_index)

            # Construir prompt contextual para el modelo con el canal de intención
            messages = self._build_turn_prompt(
                task_id=tid,
                goal=user_goal,
                active_step=active_step,
                last_result=last_exec_result
            )

            # Inferencia con LocalLLMClient / Free Model Cascade
            logger.debug(f"[Turno {turn_counter}] Solicitando decisión al LLM para paso {active_step.step_index}...")
            llm_response = self.llm_client.chat(messages=messages)
            raw_content = llm_response.content

            # Parsear canal de intención (Commentary/Thought Channel)
            intent_payload = self._parse_intent_payload(raw_content)
            if not intent_payload:
                logger.warning(f"[Turno {turn_counter}] Respuesta no cumplió esquema JSON estricto. Reintentando...")
                last_exec_result = ExecutionResult(
                    success=False,
                    output="",
                    error="Error de formato: La respuesta no fue un JSON válido con campos 'thought', 'intent', 'action' y 'params'. Corrige el formato.",
                    exit_code=400
                )
                continue

            thought = intent_payload.get("thought", "")
            intent = intent_payload.get("intent", "")
            action = intent_payload.get("action", "")
            params = intent_payload.get("params", {})

            # Notificar ganchos de observabilidad
            if self.on_thought:
                self.on_thought(thought)
            if self.on_intent:
                self.on_intent(intent)
            if self.on_action:
                self.on_action(action, params)

            # Manejo de Acciones Especiales de Control
            if action in ("finish", "complete_task"):
                final_summary = params.get("final_result", intent or thought)
                self.state_manager.mark_step_completed(tid, active_step.step_index, "Paso finalizado por meta global.")
                self.state_manager.set_task_status(tid, TaskStatus.COMPLETED)
                
                # Registrar turno final
                self.state_manager.record_turn(tid, TurnRecord(
                    turn_index=turn_counter,
                    step_index=active_step.step_index,
                    thought=thought,
                    intent=intent,
                    action=action,
                    params=params,
                    success=True,
                    output=final_summary
                ))
                break

            if action == "complete_step":
                step_summary = params.get("summary", intent or "Paso completado.")
                self.state_manager.mark_step_completed(tid, active_step.step_index, step_summary)
                last_exec_result = None  # Reiniciar contexto para el nuevo paso
                
                self.state_manager.record_turn(tid, TurnRecord(
                    turn_index=turn_counter,
                    step_index=active_step.step_index,
                    thought=thought,
                    intent=intent,
                    action=action,
                    params=params,
                    success=True,
                    output=f"Paso {active_step.step_index} completado: {step_summary}"
                ))
                continue

            # Ejecutar herramienta a través del ExecutionEngine
            exec_result = self.engine.execute_action(action, params)
            last_exec_result = exec_result

            if self.on_result:
                self.on_result(exec_result)

            # Validación de Estado y Formulación de Hipótesis ante Fallos
            if not exec_result.success:
                # Si falló: extraer o formular hipótesis desde el thought
                hypothesis = thought if ("porque" in thought.lower() or "error" in thought.lower() or "hipótesis" in thought.lower()) else f"Fallo al ejecutar {action}: {exec_result.error}"
                retries = self.state_manager.record_step_failure(
                    task_id=tid,
                    step_index=active_step.step_index,
                    error=exec_result.error or "Error desconocido",
                    hypothesis=hypothesis,
                    mark_failed=(active_step.retry_count + 1 >= self.max_retries_per_step)
                )
                logger.warning(
                    f"⚠️ [Fallo en Paso {active_step.step_index}] Reintento {retries}/{self.max_retries_per_step}. "
                    f"Hipótesis formulada: {hypothesis}"
                )
            else:
                logger.info(f"✅ [Éxito en Acción '{action}'] Salida: {exec_result.output[:120]}...")

            # Persistir turno completo en SQLite
            self.state_manager.record_turn(tid, TurnRecord(
                turn_index=turn_counter,
                step_index=active_step.step_index,
                thought=thought,
                intent=intent,
                action=action,
                params=params,
                success=exec_result.success,
                output=exec_result.output,
                error=exec_result.error,
                exit_code=exec_result.exit_code,
                duration=exec_result.duration
            ))

        duration = time.time() - start_time
        all_steps = self.state_manager.get_plan_steps(tid)
        completed_count = sum(1 for s in all_steps if s.status == StepStatus.COMPLETED)
        is_success = (completed_count == len(all_steps)) and len(all_steps) > 0

        history = self.state_manager.get_recent_turns(tid, limit=turn_counter)

        return LoopResult(
            task_id=tid,
            success=is_success,
            final_output=final_summary or (f"Completados {completed_count}/{len(all_steps)} pasos."),
            steps_completed=completed_count,
            total_steps=len(all_steps),
            total_turns=turn_counter,
            duration=duration,
            history=history
        )

    def _generate_plan(self, user_goal: str) -> List[PlanStep]:
        """Solicita al LLM la descomposición inicial de la meta en pasos atómicos."""
        messages = [
            {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
            {"role": "user", "content": f"Diseña un plan de ejecución estructurado para esta meta:\n{user_goal}"}
        ]
        try:
            res = self.llm_client.chat(messages=messages)
            raw = res.content
            # Extraer JSON de la respuesta
            json_str = self._extract_json_block(raw)
            if json_str:
                data = json.loads(json_str)
                raw_steps = data.get("steps", [])
                if raw_steps:
                    return [
                        PlanStep(
                            step_index=s.get("step_index", i + 1),
                            title=s.get("title", f"Paso {i + 1}"),
                            description=s.get("description", "")
                        )
                        for i, s in enumerate(raw_steps)
                    ]
        except Exception as e:
            logger.warning(f"Error generando plan con LLM: {e}. Usando plan determinista por defecto.")

        # Plan de contingencia determinista si el LLM falla
        return [
            PlanStep(step_index=1, title="Diagnóstico y Preparación", description=f"Preparar el entorno para: {user_goal}"),
            PlanStep(step_index=2, title="Ejecución de la Tarea", description=f"Implementar y ejecutar la solución."),
            PlanStep(step_index=3, title="Verificación Final", description=f"Comprobar los resultados obtenidos.")
        ]

    def _build_turn_prompt(
        self,
        task_id: str,
        goal: str,
        active_step: PlanStep,
        last_result: Optional[ExecutionResult]
    ) -> List[Dict[str, str]]:
        """Construye el prompt contextual inyectando el canal de intención y el estado actual."""
        system_content = MUSE_SPARK_SYSTEM_PROMPT.replace(
            "{tools_schema}", self.registry.get_schema_text()
        )

        plan_summary = self.state_manager.get_plan_summary_text(task_id)
        recent_turns = self.state_manager.get_recent_turns(task_id, limit=3)

        user_content_parts = [
            f"META GLOBAL DEL USUARIO: {goal}",
            "",
            "--- PROGRESO ACTUAL DEL PLAN ---",
            plan_summary,
            "",
            f"--- PASO ACTIVO: Paso {active_step.step_index}: {active_step.title} ---",
            f"Descripción del paso: {active_step.description}"
        ]

        # Si el paso está en reintento, exigir hipótesis explícita
        if active_step.retry_count > 0 and active_step.hypothesis:
            user_content_parts.append(
                f"\n⚠️ AVISO DE REINTENTO ({active_step.retry_count}/{self.max_retries_per_step}):\n"
                f"El intento previo falló. Hipótesis previa registrada: {active_step.hypothesis}\n"
                "Formula en tu 'thought' un diagnóstico certero y ejecuta una corrección real en tus 'params'."
            )

        # Contexto del resultado de la última acción ejecutada
        if last_result is not None:
            user_content_parts.append(
                f"\n--- RESULTADO DE LA ACCIÓN PREVIA ---\n"
                f"{last_result.to_context_str()}"
            )

        user_content_parts.append(
            "\nGenera tu respuesta en el esquema JSON estricto con 'thought', 'intent', 'action' y 'params'."
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "\n".join(user_content_parts)}
        ]

    def _parse_intent_payload(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Valida y extrae el esquema JSON estricto de intención y pensamiento.
        """
        if not raw_text or not isinstance(raw_text, str):
            return None

        json_str = self._extract_json_block(raw_text)
        if not json_str:
            return None

        try:
            payload = json.loads(json_str)
            if not isinstance(payload, dict):
                return None

            # Validar claves indispensables
            required_keys = {"thought", "intent", "action", "params"}
            if not required_keys.issubset(payload.keys()):
                # Si falta action o params, intentar ajustar
                if "action" not in payload and "tool" in payload:
                    payload["action"] = payload["tool"]
                if "params" not in payload:
                    payload["params"] = payload.get("arguments", payload.get("parameters", {}))
                if "intent" not in payload:
                    payload["intent"] = payload.get("thought", "")

            if "action" in payload and "params" in payload:
                if not isinstance(payload.get("params"), dict):
                    payload["params"] = {}
                return payload

        except Exception as e:
            logger.debug(f"Error parseando JSON de intención: {e}")

        return None

    def _extract_json_block(self, text: str) -> Optional[str]:
        """Extrae el contenido JSON delimitado por ```json ... ``` o llaves planas {}."""
        # Intento 1: Bloque de código ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Intento 2: Buscar el primer objeto JSON balanceado con llaves
        start_idx = text.find("{")
        if start_idx != -1:
            decoder = json.JSONDecoder()
            try:
                obj, end_idx = decoder.raw_decode(text[start_idx:])
                if isinstance(obj, dict):
                    return text[start_idx:start_idx + end_idx].strip()
            except Exception:
                pass

        return None
