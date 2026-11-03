"""
Módulo Goldfish Critic (Google EGM - Evaluation-Guided Mechanism).
Auditor pre-ejecución stateless (zero-context) que analiza el plan emitido por el MacroEngine
antes de que pase al MicroEngine o se ejecuten acciones.

Detecta bloqueantes críticos:
1. Rutas relativas o no procesadas/blindadas por `utils.bypass.LiteralBypass`.
2. Ausencia de timeouts explícitos en llamadas a ventanas o APIs de Win32 (riesgo de bloqueo infinito).
3. Supuestos de dependencias binarias o herramientas externas no comprobadas previamente.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.bypass import LiteralBypass
from utils.logger import log


@dataclass
class GoldfishAuditResult:
    """Resultado estructurado de la auditoría stateless pre-ejecución."""
    approved: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    critique: str = ""
    suggested_fixes: List[str] = field(default_factory=list)
    checked_rules: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "critique": self.critique,
            "suggested_fixes": self.suggested_fixes,
            "checked_rules": self.checked_rules,
        }


class GoldfishCritic:
    """
    Sub-agente auditor stateless (memoria tipo Pez Dorado / EGM).
    Evalúa exclusivamente el esqueleto y las tareas propuestas sin dejarse sesgar
    por el historial conversacional ni por promesas del LLM.
    """

    # Binarios externos comunes que requieren comprobación previa
    EXTERNAL_BINARIES = {
        "ffmpeg", "docker", "git", "node", "npm", "cargo", "openscad",
        "code", "blender", "curl", "adb", "qemu", "pandoc", "rustc"
    }

    # Palabras clave asociadas a operaciones Win32 / GUI de escritorio
    WIN32_KEYWORDS = {
        "win32gui", "findwindow", "setforegroundwindow", "desktop_app_live_type",
        "desktop_live_operator", "enumwindows", "getwindowtext", "pyautogui",
        "sendmessage", "postmessage", "ventanas", "ventana win32", "appactivate"
    }

    # Palabras clave de comprobación de dependencias
    CHECK_KEYWORDS = {
        "where", "get-command", "which", "--version", "-v", "verificar", "check", "exists", "inspect"
    }

    def __init__(self, api_base_url: Optional[str] = None) -> None:
        self.api_base_url = api_base_url or os.getenv("MMAE_API_URL", "http://localhost:8000/v1")
        self.bypass = LiteralBypass()

    def audit_plan(
        self,
        skeleton: str,
        literals: Optional[List[str]] = None,
        tasks: Optional[List[Dict[str, Any]]] = None,
        strict_dependencies: bool = False,
    ) -> GoldfishAuditResult:
        """
        Ejecuta la auditoría estricta zero-context sobre el esqueleto macro.
        Si encuentra cualquier bloqueante crítico, `approved` será False.
        """
        literals = literals or []
        blockers: List[str] = []
        warnings: List[str] = []
        suggested_fixes: List[str] = []
        checked_rules: Dict[str, bool] = {}

        combined_text = skeleton
        if tasks:
            tasks_desc = " ".join([t.get("description", "") for t in tasks])
            combined_text = f"{skeleton}\n{tasks_desc}"

        # -------------------------------------------------------------
        # Regla 1: Auditoría de Rutas y Literales (bypass.py)
        # -------------------------------------------------------------
        rule_paths_ok = True
        
        # Detectar rutas absolutas que NO estén usando el formato de token bypass
        path_pattern = re.compile(self.bypass.patterns["file_paths"], re.IGNORECASE)
        raw_paths_found = path_pattern.findall(combined_text)

        # Si hay rutas raw encontradas pero literals está vacío o ninguna coincide con los tokens
        has_bypass_tokens = "__LITERAL_TOKEN_" in combined_text
        if raw_paths_found and not has_bypass_tokens and not literals:
            rule_paths_ok = False
            blockers.append(
                f"Detectadas {len(raw_paths_found)} ruta(s) sin aislar mediante LiteralBypass: "
                f"{raw_paths_found[:2]}. Deben ser protegidas con extract_and_shield()."
            )
            suggested_fixes.append(
                "Pasa el prompt y rutas por LiteralBypass antes de emitir la planificación."
            )

        # Detectar rutas relativas ambiguas (ej: data/test.txt o .\archivo.py)
        relative_path_pattern = re.compile(r"(?:\s|^)(?:\.{1,2}[\\/]|[\w-]+\\[\w-]+|[\w-]+/[\w-]+)(?:\.[\w]+)", re.MULTILINE)
        relative_matches = relative_path_pattern.findall(combined_text)
        # Filtrar extensiones comunes falsas o keywords
        filtered_rel = [m.strip() for m in relative_matches if not m.strip().startswith("http") and not any(kw in m.lower() for kw in ("core/", "utils/", "skills/"))]
        if filtered_rel:
            warnings.append(
                f"Detectadas posibles rutas relativas no canónicas: {filtered_rel[:3]}. "
                "Se aconseja convertirlas a rutas absolutas seguras."
            )

        checked_rules["literal_bypass_paths"] = rule_paths_ok

        # -------------------------------------------------------------
        # Regla 2: Timeouts en Ventanas y APIs Win32
        # -------------------------------------------------------------
        rule_timeouts_ok = True
        lower_text = combined_text.lower()
        has_win32_action = any(kw in lower_text for kw in self.WIN32_KEYWORDS)

        if has_win32_action:
            # Comprobar si existe indicación de timeout
            has_timeout = any(kw in lower_text for kw in (
                "timeout", "tiempo límite", "max_wait", "segundos", "seconds", "retries", "reintentos"
            ))
            if not has_timeout:
                rule_timeouts_ok = False
                blockers.append(
                    "Operación de interfaz gráfica o Win32 detectada sin timeout explícito. "
                    "Riesgo de bloqueo permanente (freeze) si la ventana no responde."
                )
                suggested_fixes.append(
                    "Incluye un parámetro de timeout explícito (ej. timeout=10s) en los pasos de búsqueda o interacción con ventanas."
                )

        checked_rules["win32_timeout_safety"] = rule_timeouts_ok

        # -------------------------------------------------------------
        # Regla 3: Supuestos de Dependencias No Comprobadas
        # -------------------------------------------------------------
        rule_dependencies_ok = True
        referenced_binaries: List[str] = []
        for b in self.EXTERNAL_BINARIES:
            # Buscar mención como comando o palabra clave aislada
            if re.search(rf"\b{b}\b", lower_text):
                referenced_binaries.append(b)

        if referenced_binaries:
            has_verification_step = any(kw in lower_text for kw in self.CHECK_KEYWORDS)
            if not has_verification_step:
                msg = (
                    f"El plan asume la existencia de binarios externos ({', '.join(referenced_binaries)}) "
                    f"sin un paso previo de verificación de dependencias (ej. 'where {referenced_binaries[0]}')."
                )
                if strict_dependencies:
                    rule_dependencies_ok = False
                    blockers.append(msg)
                else:
                    warnings.append(msg)
                suggested_fixes.append(
                    f"Añade un paso inicial para comprobar la disponibilidad de {referenced_binaries[0]} antes de ejecutarlo."
                )

        checked_rules["unverified_dependencies"] = rule_dependencies_ok

        # -------------------------------------------------------------
        # Decisión Final Stateless
        # -------------------------------------------------------------
        approved = (len(blockers) == 0)

        critique_parts: List[str] = []
        if approved:
            critique_parts.append("Plan aprobado por Goldfish Critic EGM.")
            if warnings:
                critique_parts.append(f"Se emitieron {len(warnings)} advertencia(s) no bloqueantes.")
        else:
            critique_parts.append(
                f"RECHAZADO: Se detectaron {len(blockers)} bloqueante(s) crítico(s) pre-ejecución."
            )

        result = GoldfishAuditResult(
            approved=approved,
            blockers=blockers,
            warnings=warnings,
            critique=" ".join(critique_parts),
            suggested_fixes=suggested_fixes,
            checked_rules=checked_rules,
        )

        log.info(
            f"🔍 [Goldfish Critic]: Aprobado={result.approved} | "
            f"Bloqueantes={len(result.blockers)} | Advertencias={len(result.warnings)}"
        )
        if not result.approved:
            for b in result.blockers:
                log.warning(f"   🚫 [Bloqueante]: {b}")

        return result


__all__ = ["GoldfishCritic", "GoldfishAuditResult"]
