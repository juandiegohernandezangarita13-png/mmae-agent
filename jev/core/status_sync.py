"""
Sincronizador global de estado para el agente MMAE / JEV.
Permite que la terminal interactiva (estilo Claude Code), tareas en segundo plano
y el widget flotante de escritorio compartan el estado de ejecución en tiempo real.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_BASE_DIR = Path(__file__).resolve().parents[2]
_venv_site = _BASE_DIR / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

_STATUS_FILE = _BASE_DIR / "data" / ".agent_status.json"

_current_mem_status: Dict[str, Any] = {
    "state": "idle",
    "running": False,
    "task": "",
    "thought": "",
    "tool": "",
    "tool_args": "",
    "tool_in_progress": False,
    "last_ok": None,
    "updated_at": 0.0,
}


def set_agent_status(
    state: str = "idle",
    running: bool = False,
    task: Optional[str] = None,
    thought: Optional[str] = None,
    tool: Optional[str] = None,
    tool_args: Optional[str] = None,
    tool_in_progress: Optional[bool] = None,
    last_ok: Optional[bool] = None,
) -> None:
    """Actualiza el estado de ejecución y lo persiste de forma atómica para el widget."""
    global _current_mem_status
    _current_mem_status["state"] = state
    _current_mem_status["running"] = running
    if task is not None:
        _current_mem_status["task"] = task
    if thought is not None:
        _current_mem_status["thought"] = thought
    if tool is not None:
        _current_mem_status["tool"] = tool
    if tool_args is not None:
        _current_mem_status["tool_args"] = tool_args
    if tool_in_progress is not None:
        _current_mem_status["tool_in_progress"] = tool_in_progress
    if last_ok is not None:
        _current_mem_status["last_ok"] = last_ok
    _current_mem_status["updated_at"] = time.time()

    try:
        _STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATUS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_current_mem_status, f, ensure_ascii=False)
        tmp.replace(_STATUS_FILE)
    except Exception:
        pass


def get_agent_status() -> Dict[str, Any]:
    """Obtiene el último estado reportado por cualquier proceso del agente."""
    global _current_mem_status
    try:
        if _STATUS_FILE.exists():
            with open(_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Si no se ha actualizado en más de 20 segundos y marcaba running, reset a idle
                    now = time.time()
                    updated = float(data.get("updated_at", 0))
                    if data.get("running") and (now - updated > 25.0):
                        data["running"] = False
                        data["state"] = "idle"
                    return data
    except Exception:
        pass
    return _current_mem_status
