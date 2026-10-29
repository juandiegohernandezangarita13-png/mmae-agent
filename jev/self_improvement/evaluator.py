"""
Módulo de evaluación y reflexión para automejora de JEV.
Analiza la traza de ejecución de tareas para extraer lecciones,
detectar carencias de herramientas (Tool Gap Analysis) y disparar
automáticamente la búsqueda e instalación de nuevas habilidades en caliente.
"""
from typing import Dict, Any, List, Optional, Callable
import json

from jev.core.memory import AgentMemory
from jev.core.llm_client import LocalLLMClient


class SelfImprovementEvaluator:
    """Evalúa ejecuciones, genera reglas heurísticas y resuelve carencias de herramientas."""

    def __init__(
        self,
        memory: AgentMemory,
        llm_client: LocalLLMClient,
        hub_manager: Optional[Any] = None,
        qa_auditor: Optional[Any] = None,
        on_thought: Optional[Callable[[str], None]] = None
    ):
        self.memory = memory
        self.llm = llm_client
        self.hub_manager = hub_manager
        self.qa_auditor = qa_auditor
        self.on_thought = on_thought or (lambda t: None)

    def _get_hub_manager(self) -> Optional[Any]:
        """Obtiene o instancia perezosamente el SkillHubManagerTool."""
        if self.hub_manager is None:
            try:
                from jev.tools.custom.skill_hub_manager import SkillHubManagerTool
                self.hub_manager = SkillHubManagerTool()
            except Exception:
                pass
        return self.hub_manager

    def _get_qa_auditor(self) -> Optional[Any]:
        """Obtiene o instancia perezosamente el AgentQAAuditor."""
        if self.qa_auditor is None:
            try:
                from jev.self_improvement.qa_auditor import AgentQAAuditor
                self.qa_auditor = AgentQAAuditor(memory_dir=self.memory.memory_dir)
            except Exception:
                pass
        return self.qa_auditor

    def resolve_tool_gap(self, gap_description: str, task_context: str = "") -> Optional[Dict[str, Any]]:
        """
        Dispara automáticamente la búsqueda e instalación de una habilidad en caliente
        para subsanar una carencia de herramientas detectada.
        """
        hub = self._get_hub_manager()
        if not hub or not gap_description:
            return None

        res = hub.execute(action="search_and_install", task_description=gap_description)
        if res.success and res.data:
            skill_name = res.data.get("skill_name", "")
            rule_text = f"Carencia '{gap_description}' resuelta: habilidad '{skill_name}' auto-instalada en caliente e inyectada al registro."
            self.memory.add_learned_lesson(category="Herramientas", rule=rule_text, context=task_context)
            event_notice = f"⚡ [Skill Auto-Injected]: Habilidad '{skill_name}' instalada y lista para invocación."
            self.on_thought(event_notice)
            return res.data
        return None

    def reflect_and_learn(
        self,
        task: str,
        execution_log: List[Dict[str, Any]],
        success: bool
    ) -> Optional[str]:
        """
        Analiza si hubo errores en la ejecución o si se descubrió una mejor forma de operar.
        Si detecta una carencia de herramientas en el bucle, dispara automáticamente
        la búsqueda e instalación en el Hub Comunitario.
        """
        # Filtrar herramientas que hayan devuelto error
        error_events = []
        for step in execution_log:
            if step.get("role") == "tool":
                content = str(step.get("content", ""))
                if "ERROR" in content or "Traceback" in content or "Falló" in content:
                    error_events.append({
                        "tool": step.get("name"),
                        "error": content[:250]
                    })

        # Si no hubo errores y fue exitosa, no forzamos una lección a menos que haya sido una tarea compleja
        if not error_events and success:
            return None

        # Preparar prompt de reflexión
        prompt_reflection = f"""Actúa como el módulo metacognitivo de automejora de JEV.
TAREA OBJETIVO: {task}
RESULTADO: {"ÉXITO" if success else "FALLO"}
ERRORES ENCONTRADOS DURANTE LA EJECUCIÓN:
{json.dumps(error_events, indent=2, ensure_ascii=False) if error_events else "Ningún error explícito registrado."}

Tu objetivo es formular UNA regla concisa (máximo 2 líneas) para recordar en el futuro y no cometer el mismo error o ser más eficiente.
Además, si durante la ejecución se manifestó la falta o carencia de una herramienta especializada, identifícala en 'tool_gap'.
Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
{{
  "category": "Pantalla" | "Archivos" | "Shell" | "Web" | "Estrategia" | "Herramientas",
  "rule": "Regla clara y accionable para futuras tareas.",
  "tool_gap": "Descripción breve de la herramienta o capacidad faltante si la hubo, o null si no se requería."
}}
"""
        try:
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": "Eres un módulo de reflexión metacognitiva que genera lecciones aprendidas en formato JSON estricto."},
                    {"role": "user", "content": prompt_reflection}
                ]
            )
            raw = response.content.strip()
            # Limpiar posible markdown
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            data = json.loads(raw)
            category = data.get("category", "Estrategia")
            rule = data.get("rule", "")
            tool_gap = data.get("tool_gap")

            # Tool Gap Analysis: si se detectó carencia, disparar búsqueda e instalación en el Hub
            if not tool_gap and (category == "Herramientas" or "falta" in rule.lower() or "carencia" in rule.lower() or "missing" in rule.lower()):
                tool_gap = task

            if tool_gap:
                install_data = self.resolve_tool_gap(str(tool_gap), task_context=task)
                if install_data:
                    installed_skill = install_data.get("skill_name", "")
                    rule = f"{rule} (Auto-Inyectada: {installed_skill})"

            # Mitigación de Context Poisoning: validar calidad antes de persistir
            if rule and len(rule.strip()) >= 10:
                trivial_phrases = ["hacer bien", "no fallar", "hacer las cosas bien", "ejecutar correctamente"]
                if not any(tp in rule.lower() for tp in trivial_phrases):
                    self.memory.add_learned_lesson(trigger_context=category, lesson=rule, context=task)
                    return f"[{category}]: {rule}"
        except Exception:
            # En caso de que el modelo devuelva texto no JSON, podemos guardar una lección simple si hubo error
            if error_events:
                first_err = error_events[0]
                rule = f"Cuidado con la herramienta '{first_err['tool']}': verificar argumentos y contexto previo."
                if "no encontrada" in str(first_err.get("error", "")).lower() or "missing" in str(first_err.get("error", "")).lower():
                    self.resolve_tool_gap(task, task_context=task)
                self.memory.add_learned_lesson(trigger_context="Herramientas", lesson=rule, context=task)
                return rule

        return None
