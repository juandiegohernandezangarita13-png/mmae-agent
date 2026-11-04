"""
Árbol de Componentes del Harness (c1..c8) para Agentes Autónomos.
Implementa una superficie mutable, diffable y serializable inspirada en Harness².

Componentes expuestos:
- c1: system_prompt   (Contexto: Directivas cognitivas base)
- c2: guardrails      (Contexto: Reglas de seguridad e invariantes)
- c3: memory_guidance (Contexto: Políticas de retención y retrieval)
- c4: skills          (Contexto: Capacidades modulares activas)
- c5: tool_guidance   (Herramientas: Directivas de uso e interfaces)
- c6: scripts         (Herramientas: Código Python local ejecutable)
- c7: subagents       (Delegación: Especialistas y roles delegados)
- c8: plugins         (Middleware: Hooks de ciclo de vida)

Regla de edición: "Omitted-is-inherited" (lo omitido en una propuesta se hereda del harness base).
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set


class HarnessComponent(str, Enum):
    SYSTEM_PROMPT = "system_prompt"
    GUARDRAILS = "guardrails"
    MEMORY_GUIDANCE = "memory_guidance"
    SKILLS = "skills"
    TOOL_GUIDANCE = "tool_guidance"
    SCRIPTS = "scripts"
    SUBAGENTS = "subagents"
    PLUGINS = "plugins"


@dataclass
class HarnessTree:
    """
    Representa el estado completo de un Harness de agente.
    Cada componente es un diccionario de rutas relativas a contenidos de texto,
    o bloques de configuración declarativa.
    """
    version: str = "harness-1.0"
    system_prompt: str = ""
    guardrails: List[str] = field(default_factory=list)
    memory_guidance: str = ""
    skills: Dict[str, str] = field(default_factory=dict)         # {skill_name: instructions}
    tool_guidance: Dict[str, str] = field(default_factory=dict)   # {tool_name: instructions}
    scripts: Dict[str, str] = field(default_factory=dict)         # {script_name.py: code}
    subagents: Dict[str, str] = field(default_factory=dict)       # {agent_name: prompt_role}
    plugins: Dict[str, str] = field(default_factory=dict)         # {hook_name: logic_or_config}

    @classmethod
    def create_default(cls) -> "HarnessTree":
        """Crea un Harness base con la configuración estándar de MMAE."""
        return cls(
            version="harness-1.0",
            system_prompt=(
                "Eres MMAE (Multi-Model Autonomous Engine), un ingeniero de sistemas de IA y agente autónomo "
                "de ejecución determinista en Windows. Tu objetivo es resolver tareas complejas mediante "
                "planificación macro y ejecución micro paso a paso."
            ),
            guardrails=[
                "Usa siempre rutas absolutas procesadas por bypass.py para evitar comillas corruptas.",
                "Valida la existencia física de recursos antes de asumir que existen.",
                "En ejecuciones por lotes o consultas múltiples, emite scripts para script_runner.",
                "No alucines el éxito: verifica el código de salida y archivos modificados físicamente.",
            ],
            memory_guidance="Prioriza procedimientos con alto confidence_score; penaliza aquellos con decaimiento cognitivo.",
            skills={
                "windows_automation": "Automatización Win32 mediante powershell y subprocess con timeouts estrictos.",
                "python_execution": "Ejecución local segura vía script_runner con captura compacta en JSON.",
            },
            tool_guidance={
                "terminal": "Ejecuta comandos CLI con timeout explícito y captura de salida.",
                "execute_script": "Ejecuta scripts Python locales en lote y devuelve un JSON condensado.",
                "read_file": "Lectura segura con codificación UTF-8.",
                "write_file": "Escritura atómica de archivos con creación automática de directorios padres.",
            },
            scripts={},
            subagents={
                "critic": "Auditor pre-ejecución stateless (GoldfishCritic) sin contexto previo.",
            },
            plugins={
                "on_tool_call": "Validación de sintaxis y bypass de literales.",
                "on_step_finish": "Registro temporal con ExecutionTimer.",
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el árbol a un diccionario estándar."""
        return {
            "version": self.version,
            "system_prompt": self.system_prompt,
            "guardrails": list(self.guardrails),
            "memory_guidance": self.memory_guidance,
            "skills": dict(self.skills),
            "tool_guidance": dict(self.tool_guidance),
            "scripts": dict(self.scripts),
            "subagents": dict(self.subagents),
            "plugins": dict(self.plugins),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HarnessTree":
        """Reconstruye el árbol desde un diccionario."""
        return cls(
            version=data.get("version", "harness-1.0"),
            system_prompt=data.get("system_prompt", ""),
            guardrails=list(data.get("guardrails", [])),
            memory_guidance=data.get("memory_guidance", ""),
            skills=dict(data.get("skills", {})),
            tool_guidance=dict(data.get("tool_guidance", {})),
            scripts=dict(data.get("scripts", {})),
            subagents=dict(data.get("subagents", {})),
            plugins=dict(data.get("plugins", {})),
        )

    def write_to_dir(self, target_dir: Path) -> None:
        """Escribe todos los componentes en una estructura de carpetas en disco."""
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # c1: System Prompt
        (target_dir / "system_prompt.txt").write_text(self.system_prompt, encoding="utf-8")

        # c2: Guardrails
        (target_dir / "guardrails.json").write_text(
            json.dumps(self.guardrails, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # c3: Memory guidance
        (target_dir / "memory_guidance.txt").write_text(self.memory_guidance, encoding="utf-8")

        # c4: Skills
        skills_dir = target_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for name, content in self.skills.items():
            (skills_dir / f"{name}.md").write_text(content, encoding="utf-8")

        # c5: Tool guidance
        tools_dir = target_dir / "tools"
        tools_dir.mkdir(exist_ok=True)
        for name, content in self.tool_guidance.items():
            (tools_dir / f"{name}.txt").write_text(content, encoding="utf-8")

        # c6: Scripts
        scripts_dir = target_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for name, code in self.scripts.items():
            (scripts_dir / name).write_text(code, encoding="utf-8")

        # c7: Subagents
        agents_dir = target_dir / "subagents"
        agents_dir.mkdir(exist_ok=True)
        for name, prompt in self.subagents.items():
            (agents_dir / f"{name}.txt").write_text(prompt, encoding="utf-8")

        # c8: Plugins
        plugins_dir = target_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        for name, cfg in self.plugins.items():
            (plugins_dir / f"{name}.txt").write_text(cfg, encoding="utf-8")

    @classmethod
    def read_from_dir(cls, source_dir: Path) -> "HarnessTree":
        """Lee un árbol de componentes desde un directorio."""
        source_dir = Path(source_dir)
        if not source_dir.exists():
            return cls.create_default()

        sys_prompt = ""
        p = source_dir / "system_prompt.txt"
        if p.is_file():
            sys_prompt = p.read_text(encoding="utf-8")

        guardrails = []
        p = source_dir / "guardrails.json"
        if p.is_file():
            try:
                guardrails = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass

        mem_guidance = ""
        p = source_dir / "memory_guidance.txt"
        if p.is_file():
            mem_guidance = p.read_text(encoding="utf-8")

        skills = {}
        s_dir = source_dir / "skills"
        if s_dir.is_dir():
            for f in s_dir.glob("*.md"):
                skills[f.stem] = f.read_text(encoding="utf-8")

        tool_guidance = {}
        t_dir = source_dir / "tools"
        if t_dir.is_dir():
            for f in t_dir.glob("*.txt"):
                tool_guidance[f.stem] = f.read_text(encoding="utf-8")

        scripts = {}
        sc_dir = source_dir / "scripts"
        if sc_dir.is_dir():
            for f in sc_dir.glob("*.py"):
                scripts[f.name] = f.read_text(encoding="utf-8")

        subagents = {}
        a_dir = source_dir / "subagents"
        if a_dir.is_dir():
            for f in a_dir.glob("*.txt"):
                subagents[f.stem] = f.read_text(encoding="utf-8")

        plugins = {}
        pl_dir = source_dir / "plugins"
        if pl_dir.is_dir():
            for f in pl_dir.glob("*.txt"):
                plugins[f.stem] = f.read_text(encoding="utf-8")

        return cls(
            system_prompt=sys_prompt,
            guardrails=guardrails,
            memory_guidance=mem_guidance,
            skills=skills,
            tool_guidance=tool_guidance,
            scripts=scripts,
            subagents=subagents,
            plugins=plugins,
        )

    def patch(self, delta: Dict[str, Any]) -> "HarnessTree":
        """
        Aplica una propuesta de cambio respetando la regla "omitted-is-inherited".
        Solo se actualizan los campos presentes y no nulos en delta.
        """
        new_tree = copy.deepcopy(self)

        if "system_prompt" in delta and delta["system_prompt"]:
            new_tree.system_prompt = str(delta["system_prompt"])

        if "guardrails" in delta and isinstance(delta["guardrails"], list):
            # Agregar nuevos guardrails preservando los existentes
            current = set(new_tree.guardrails)
            for g in delta["guardrails"]:
                if g not in current:
                    new_tree.guardrails.append(g)

        if "memory_guidance" in delta and delta["memory_guidance"]:
            new_tree.memory_guidance = str(delta["memory_guidance"])

        if "skills" in delta and isinstance(delta["skills"], dict):
            new_tree.skills.update(delta["skills"])

        if "tool_guidance" in delta and isinstance(delta["tool_guidance"], dict):
            new_tree.tool_guidance.update(delta["tool_guidance"])

        if "scripts" in delta and isinstance(delta["scripts"], dict):
            new_tree.scripts.update(delta["scripts"])

        if "subagents" in delta and isinstance(delta["subagents"], dict):
            new_tree.subagents.update(delta["subagents"])

        if "plugins" in delta and isinstance(delta["plugins"], dict):
            new_tree.plugins.update(delta["plugins"])

        return new_tree

    def diff(self, other: "HarnessTree") -> Dict[str, List[str]]:
        """Calcula las diferencias entre este harness y otro."""
        added = []
        removed = []
        modified = []

        if self.system_prompt != other.system_prompt:
            modified.append("system_prompt")

        if set(self.guardrails) != set(other.guardrails):
            diff_g = set(other.guardrails) - set(self.guardrails)
            if diff_g:
                added.append(f"guardrails (+{len(diff_g)})")
            diff_rem = set(self.guardrails) - set(other.guardrails)
            if diff_rem:
                removed.append(f"guardrails (-{len(diff_rem)})")

        for key in ("skills", "tool_guidance", "scripts", "subagents", "plugins"):
            self_map: dict = getattr(self, key)
            other_map: dict = getattr(other, key)

            for k in other_map:
                if k not in self_map:
                    added.append(f"{key}/{k}")
                elif self_map[k] != other_map[k]:
                    modified.append(f"{key}/{k}")

            for k in self_map:
                if k not in other_map:
                    removed.append(f"{key}/{k}")

        return {"added": added, "removed": removed, "modified": modified}

    def inventory(self) -> str:
        """Censo sintético de una línea de los componentes del harness."""
        parts = []
        if self.skills:
            parts.append(f"{len(self.skills)} skills")
        if self.scripts:
            parts.append(f"{len(self.scripts)} scripts")
        if self.subagents:
            parts.append(f"{len(self.subagents)} subagents")
        if self.guardrails:
            parts.append(f"{len(self.guardrails)} guardrails")
        total_chars = (
            len(self.system_prompt)
            + sum(len(g) for g in self.guardrails)
            + len(self.memory_guidance)
            + sum(len(v) for v in self.skills.values())
            + sum(len(v) for v in self.tool_guidance.values())
            + sum(len(v) for v in self.scripts.values())
        )
        summary = ", ".join(parts) or "configuración base"
        return f"{summary}; {total_chars:,} caracteres totales"
