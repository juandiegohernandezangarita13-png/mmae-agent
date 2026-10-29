"""
Arranque silencioso de JEV desde el acceso directo del escritorio.

Este módulo es el equivalente Windows del campo Exec de una entrada .desktop:
  * resuelve la carpeta del proyecto sin depender del directorio actual,
  * redirige stdout/stderr a data/logs/jev_launcher.log (pythonw no tiene consola),
  * impide dos instancias simultáneas mediante un mutex con nombre de Windows,
  * muestra un cuadro de diálogo legible si el arranque falla.

Por defecto arranca la Isla de escritorio (compañero flotante). Con
--classic arranca directamente la ventana JARVIS completa.

No abre ninguna ventana por sí mismo: delega en app.main().
"""
from __future__ import annotations

import ctypes
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "data" / "logs"
LOG_FILE = LOG_DIR / "jev_launcher.log"
MUTEX_NAME = "Local\\JEV_AutonomousAI_SingleInstance"

_MUTEX_HANDLE = None
_LOG_STREAM = None


def _rotate_log(max_bytes: int = 2 * 1024 * 1024) -> None:
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > max_bytes:
            backup = LOG_FILE.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_FILE.rename(backup)
    except OSError:
        pass


def _open_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_log()
    stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    stream.write("\n" + "=" * 78 + "\n")
    stream.write(f"[{datetime.now().isoformat(timespec='seconds')}] Inicio del lanzador JEV\n")
    stream.write(f"Python: {sys.executable}\nBase:   {BASE}\n")
    return stream


def _message_box(text: str, title: str = "JEV", flags: int = 0x10) -> None:
    """Muestra un cuadro de diálogo nativo (el lanzador no tiene consola)."""
    if sys.platform != "win32":
        print(text, file=sys.stderr)
        return
    try:
        ctypes.windll.user32.MessageBoxW(0, str(text), str(title), flags)
    except Exception:
        print(text, file=sys.stderr)


def _acquire_single_instance():
    """
    Crea un mutex con nombre. Devuelve el handle, o None si JEV ya está abierto.
    El handle debe mantenerse vivo mientras dure el proceso.
    """
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True  # sin mutex, mejor permitir el arranque que bloquearlo
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            if handle:
                kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return True


def _focus_existing_instance() -> bool:
    """
    Si ya hay una instancia de JEV, trae su isla (o su ventana) al frente en
    lugar de dejar al usuario con un cuadro de diálogo y sin interfaz.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        focused = False
        # La isla primero; si no existe, la ventana completa.
        for title in ("JEV Island", "JEV // Autonomous AI"):
            hwnd = user32.FindWindowW(None, title)
            if not hwnd:
                continue
            focused = True
            user32.ShowWindow(hwnd, 8)  # SW_SHOWNA (sin robar el foco)
            # HWND_TOPMOST + SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            if title != "JEV Island":
                user32.SetForegroundWindow(hwnd)
        return focused
    except Exception:
        return False


def _check_environment() -> int:
    """Modo de verificación (JEV_LAUNCHER_CHECK=1): valida sin abrir la interfaz."""
    results = []
    problems = []
    if not (BASE / "app.py").exists():
        problems.append("No se encontró app.py junto al lanzador.")
    if not (BASE / ".venv" / "Scripts" / "python.exe").exists():
        problems.append("No se encontró el entorno virtual .venv\\Scripts\\python.exe.")
    try:
        import app  # noqa: F401
        import jev_desktop  # noqa: F401
    except Exception as exc:  # pragma: no cover - depende del entorno
        problems.append(f"Fallo al importar app.py / jev_desktop.py: {exc}")
    if problems:
        for problem in problems:
            line = f"[CHECK][ERROR] {problem}"
            print(line)
            results.append(line)
        _write_check_log(results)
        return 1
    line = "[CHECK] OK: app.py importable y entorno virtual presente."
    print(line)
    results.append(line)
    _write_check_log(results)
    return 0


def _write_check_log(lines) -> None:
    """Deja constancia del modo verificación (wscript no tiene consola)."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as stream:
            stamp = datetime.now().isoformat(timespec="seconds")
            for line in lines:
                stream.write(f"[{stamp}] {line}\n")
    except OSError:
        pass


def main() -> int:
    global _MUTEX_HANDLE, _LOG_STREAM

    os.chdir(BASE)
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if os.environ.get("JEV_LAUNCHER_CHECK") == "1":
        return _check_environment()

    _LOG_STREAM = _open_log()
    sys.stdout = _LOG_STREAM
    sys.stderr = _LOG_STREAM

    _MUTEX_HANDLE = _acquire_single_instance()
    if _MUTEX_HANDLE is None:
        if _focus_existing_instance():
            print("[INFO] JEV ya estaba abierto: se ha traído su interfaz al frente.")
            return 0
        # Hay un mutex huérfano (proceso bloqueado o sin ventana): se arranca
        # una instancia nueva en lugar de dejar al usuario sin interfaz.
        print("[INFO] Instancia previa sin ventana detectable; se inicia una nueva.")

    classic = "--classic" in sys.argv[1:]
    try:
        if classic:
            from app import main as app_main

            print(f"[{datetime.now().isoformat(timespec='seconds')}] Entrando en app.main() [ventana clásica]...")
            app_main()
            print(f"[{datetime.now().isoformat(timespec='seconds')}] app.main() finalizó correctamente.")
        else:
            from jev_desktop import main as desktop_main

            print(f"[{datetime.now().isoformat(timespec='seconds')}] Entrando en jev_desktop.main() [isla]...")
            desktop_main()
            print(f"[{datetime.now().isoformat(timespec='seconds')}] jev_desktop.main() finalizó correctamente.")
        return 0
    except SystemExit as exc:
        print(f"[SALIDA] SystemExit: {exc}")
        return int(exc.code or 0)
    except Exception:
        error = traceback.format_exc()
        print(error)
        _message_box(
            "No se pudo iniciar JEV.\n\n"
            f"Revisa el registro:\n{LOG_FILE}\n\n"
            + error.strip().splitlines()[-1],
            "JEV - Error de arranque",
        )
        return 1
    finally:
        try:
            if _LOG_STREAM:
                _LOG_STREAM.flush()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
