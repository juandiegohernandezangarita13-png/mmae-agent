"""
Handler de skill_ia_en_casa — "IA EN CASA · Parte 7: 5 IAs sin tarjeta de video potente".

Catálogo de IAs locales que corren en equipos modestos (sin GPU dedicada / ~4 GB RAM):
  5. OHF-Voice/piper1-gpl      -> Texto a voz
  4. mozilla-ai/llamafile      -> Chat (LLM en un archivo)
  3. leejet/stable-diffusion.cpp -> Imágenes (C/C++)
  2. rupeshs/fastsdcpu         -> Imágenes en CPU (modo LCM, 2 GB RAM)
  1. microsoft/BitNet          -> LLM de 1 bit (bitnet.cpp)

Acciones reales (no simuladas): detección de hardware, detección de instalaciones,
instalación de Piper vía pip en el entorno actual, síntesis de voz y clonado de repos.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

SKILL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SKILL_DIR.parent.parent.parent
CATALOG_PATH = SKILL_DIR / "catalog.json"
REPOS_DIR = PROJECT_ROOT / "repos"
VOICES_DIR = PROJECT_ROOT / "data" / "piper_voices"
OUTPUT_DIR = PROJECT_ROOT / "workspace" / "audio"


def _catalog() -> Dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _hardware() -> Dict[str, Any]:
    info: Dict[str, Any] = {"ram_gb": None, "cpu_cores": None, "gpu": "desconocida"}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        info["ram_libre_gb"] = round(psutil.virtual_memory().available / (1024 ** 3), 1)
        info["cpu_cores"] = psutil.cpu_count(logical=True)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '; '"],
            capture_output=True, text=True, timeout=10,
        )
        if out.stdout.strip():
            info["gpu"] = out.stdout.strip()
    except Exception:
        pass
    gpu_txt = str(info["gpu"]).lower()
    info["gpu_dedicada"] = any(k in gpu_txt for k in ("nvidia", "geforce", "rtx", "radeon rx", "arc a"))
    return info


def _installed() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "piper": importlib.util.find_spec("piper") is not None,
        "llamafile": bool(shutil.which("llamafile")) or any(PROJECT_ROOT.glob("**/*.llamafile")),
        "sdcpp": bool(shutil.which("sd")) or (REPOS_DIR / "stable-diffusion.cpp").exists(),
        "fastsdcpu": (REPOS_DIR / "fastsdcpu").exists(),
        "bitnet": (REPOS_DIR / "BitNet").exists(),
    }
    status["prerequisitos_bitnet"] = {
        "python": True,
        "cmake": bool(shutil.which("cmake")),
        "clang": bool(shutil.which("clang")),
        "git": bool(shutil.which("git")),
    }
    return status


def _list(category: str = "") -> Dict[str, Any]:
    cat = _catalog()
    tools = cat["herramientas"]
    if category:
        tools = [t for t in tools if t["categoria"] == category.lower()]
    lines = [f"🏠 {cat['serie']} · Parte {cat['parte']} — {cat['titulo']}"]
    for t in sorted(tools, key=lambda x: x["rank"], reverse=True):
        lines.append(f"#{t['rank']} {t['repo']} · {t['para_que']} · Necesita: {', '.join(t['necesita'])}")
    lines.append(f"⚠️ {cat['aviso']}")
    return {"status": "success", "summary": "\n".join(lines), "data": {"herramientas": tools}}


def _recommend() -> Dict[str, Any]:
    hw = _hardware()
    ram = hw.get("ram_gb") or 4
    cat = _catalog()
    fits = [t for t in cat["herramientas"] if t["ram_min_gb"] <= ram]
    picks: Dict[str, str] = {}
    for t in sorted(fits, key=lambda x: x["rank"]):
        picks.setdefault(t["categoria"], t["repo"])
    if not hw.get("gpu_dedicada"):
        picks["imagenes"] = "rupeshs/fastsdcpu (modo LCM)"
    summary = (
        f"💻 Equipo: {ram} GB RAM, {hw.get('cpu_cores')} hilos, GPU: {hw.get('gpu')}\n"
        f"🎙️ Voz: {picks.get('voz', '—')}\n"
        f"💬 Chat: {picks.get('chat', '—')} (llamafile si quieres cero instalación)\n"
        f"🖼️ Imágenes: {picks.get('imagenes', '—')}"
    )
    return {"status": "success", "summary": summary, "data": {"hardware": hw, "recomendacion": picks}}


def _install_piper() -> Dict[str, Any]:
    if importlib.util.find_spec("piper") is not None:
        return {"status": "success", "summary": "Piper ya está instalado en este entorno."}
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "piper-tts"],
        capture_output=True, text=True, timeout=900,
    )
    ok = proc.returncode == 0
    return {
        "status": "success" if ok else "error",
        "summary": "Piper instalado (pip install piper-tts)." if ok else "Falló la instalación de Piper.",
        "error": None if ok else (proc.stderr or proc.stdout)[-1500:],
    }


def _speak(text: str, voice: str) -> Dict[str, Any]:
    if not text.strip():
        return {"status": "error", "error": "Falta 'text' para sintetizar."}
    if importlib.util.find_spec("piper") is None:
        inst = _install_piper()
        if inst["status"] != "success":
            return inst
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_file = VOICES_DIR / f"{voice}.onnx"
    if not model_file.exists():
        dl = subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voice, "--data-dir", str(VOICES_DIR)],
            capture_output=True, text=True, timeout=600,
        )
        if dl.returncode != 0 or not model_file.exists():
            return {"status": "error", "error": f"No se pudo descargar la voz '{voice}': {(dl.stderr or dl.stdout)[-800:]}"}
    out_wav = OUTPUT_DIR / f"piper_{int(time.time())}.wav"
    proc = subprocess.run(
        [sys.executable, "-m", "piper", "-m", str(model_file), "-f", str(out_wav), "--", text],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0 or not out_wav.exists():
        return {"status": "error", "error": (proc.stderr or proc.stdout)[-1200:]}
    return {"status": "success", "summary": f"🎙️ Audio generado con Piper ({voice}): {out_wav}", "data": {"path": str(out_wav)}}


def _clone(tool_id: str) -> Dict[str, Any]:
    tools = {t["id"]: t for t in _catalog()["herramientas"]}
    if tool_id not in tools:
        return {"status": "error", "error": f"tool_id inválido. Usa uno de: {', '.join(tools)}"}
    if not shutil.which("git"):
        return {"status": "error", "error": "git no está instalado."}
    t = tools[tool_id]
    target = REPOS_DIR / t["repo"].split("/")[-1]
    if target.exists():
        return {"status": "success", "summary": f"Ya existe: {target}. Lee {target / 'README.md'} para instalar."}
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", t["url"] + ".git", str(target)],
        capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0:
        return {"status": "error", "error": (proc.stderr or proc.stdout)[-1200:]}
    return {"status": "success", "summary": f"Clonado en {target}. Siguiente paso: seguir {target / 'README.md'}.", "data": {"path": str(target)}}


def handle(action: str = "list", tool_id: str = "", category: str = "", text: str = "",
           voice: str = "es_MX-claude-high", **_: Any) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    try:
        if action == "list":
            return _list(category)
        if action == "recommend":
            return _recommend()
        if action == "status":
            st = _installed()
            return {"status": "success", "summary": json.dumps(st, ensure_ascii=False), "data": st}
        if action == "install_piper":
            return _install_piper()
        if action == "speak":
            return _speak(text, voice)
        if action == "clone":
            return _clone(tool_id)
        return {"status": "error", "error": f"Acción desconocida: {action}"}
    except Exception as exc:  # pragma: no cover - errores de entorno
        return {"status": "error", "error": str(exc)}
