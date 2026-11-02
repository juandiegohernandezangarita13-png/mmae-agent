"""
Detector de Flapping de Herramientas y Oscilación Cíclica (core.guardrails.flapping_detector).
Identifica patrones oscilatorios nocivos como A -> B -> A -> B donde el agente salta
indeciso entre dos herramientas sin lograr avance real de estado.
"""
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import json


@dataclass
class ToolCallRecord:
    tool_name: str
    signature: str
    success: bool
    timestamp: float


class ToolFlappingDetector:
    """
    Detector de oscilación cíclica (Flapping) en invocaciones de herramientas.
    """

    def __init__(self, history_window: int = 8, min_oscillations: int = 2):
        self.history_window = history_window
        self.min_oscillations = min_oscillations
        self.history: List[ToolCallRecord] = []

    def record_call(self, tool_name: str, tool_args: Dict[str, Any], success: bool, timestamp: float) -> None:
        """Registra una llamada en el búfer de historial deslizante."""
        try:
            sig = json.dumps(tool_args, sort_keys=True)
        except Exception:
            sig = str(tool_args)

        rec = ToolCallRecord(
            tool_name=tool_name,
            signature=f"{tool_name}:{sig}",
            success=success,
            timestamp=timestamp
        )
        self.history.append(rec)
        if len(self.history) > self.history_window:
            self.history.pop(0)

    def check_flapping(self, next_tool_name: str) -> Tuple[bool, str, Optional[str]]:
        """
        Analiza el historial reciente junto a la siguiente herramienta candidata.
        Detecta patrones como:
        - Período 2 (A -> B -> A -> B)
        - Período 3 (A -> B -> C -> A -> B -> C)
        """
        tool_names = [r.tool_name for r in self.history] + [next_tool_name]
        n = len(tool_names)

        # 1. Comprobar oscilación de período 2 (mínimo 4 llamadas: A, B, A, B)
        if n >= 4:
            last4 = tool_names[-4:]
            if last4[0] == last4[2] and last4[1] == last4[3] and last4[0] != last4[1]:
                tool_a, tool_b = last4[0], last4[1]
                return (
                    True,
                    f"GUARDRAIL: Flapping detectado. Oscilación cíclica entre '{tool_a}' y '{tool_b}' ({tool_a} -> {tool_b} -> {tool_a} -> {tool_b}).",
                    f"Detén la oscilación. No alternes entre '{tool_a}' y '{tool_b}'. Plantea un enfoque completamente diferente o pide intervención."
                )

        # 2. Comprobar oscilación de período 3 (mínimo 6 llamadas: A, B, C, A, B, C)
        if n >= 6:
            last6 = tool_names[-6:]
            if (last6[0] == last6[3] and last6[1] == last6[4] and last6[2] == last6[5] and
                len({last6[0], last6[1], last6[2]}) == 3):
                a, b, c = last6[0], last6[1], last6[2]
                return (
                    True,
                    f"GUARDRAIL: Flapping de 3 pasos detectado ({a} -> {b} -> {c} -> {a} -> {b} -> {c}).",
                    "El agente se encuentra en un bucle cerrado de 3 herramientas. Cambia radicalmente de estrategia técnica."
                )

        return (False, "OK", None)

    def reset(self) -> None:
        """Limpia el historial de detección."""
        self.history.clear()
