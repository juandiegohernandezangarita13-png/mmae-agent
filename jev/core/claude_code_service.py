"""
Gestor de Ciclo de Vida y Servicio en Segundo Plano para Free-Claude-Code (FCC).
Permite iniciar, detener, supervisar y configurar el servidor proxy local de Claude Code
conectado a OpenRouter y modelos de vanguardia sin intervención manual.
"""
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
import threading
import socket
import json
import time
import os
import sys

from jev.config import default_config, BASE_DIR


class FreeClaudeCodeService:
    """Supervisa el proceso de fcc-server en segundo plano."""

    _instance: Optional["FreeClaudeCodeService"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        port: int = 8082,
        openrouter_api_key: Optional[str] = None,
        default_model: Optional[str] = None
    ):
        if getattr(self, "_initialized", False):
            return

        self.base_dir = Path(BASE_DIR)
        self.repo_dir = Path(repo_dir or (self.base_dir / "tools" / "free-claude-code"))
        self.port = int(os.getenv("FCC_PORT", port))
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.default_model = default_model or os.getenv(
            "FCC_MODEL", "open_router/anthropic/claude-3.5-sonnet"
        )
        self.process: Optional[subprocess.Popen] = None
        self.log_dir = self.base_dir / "data" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "fcc_server.log"
        self._initialized = True

    @property
    def venv_python(self) -> Path:
        """Ruta al intérprete de Python en el entorno virtual de free-claude-code."""
        if sys.platform == "win32":
            py_path = self.repo_dir / ".venv" / "Scripts" / "python.exe"
        else:
            py_path = self.repo_dir / ".venv" / "bin" / "python"
        return py_path

    @property
    def fcc_server_bin(self) -> Path:
        """Ruta al ejecutable fcc-server en el entorno virtual."""
        if sys.platform == "win32":
            bin_path = self.repo_dir / ".venv" / "Scripts" / "fcc-server.exe"
        else:
            bin_path = self.repo_dir / ".venv" / "bin" / "fcc-server"
        return bin_path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_port_in_use(self) -> bool:
        """Verifica si el puerto local está actualmente abierto y escuchando."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    def is_healthy(self) -> bool:
        """Verifica si el servidor responde correctamente a las solicitudes HTTP de salud."""
        try:
            url = f"{self.base_url}/v1/models"
            req = urllib.request.Request(url, headers={"User-Agent": "JEV-HealthChecker/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Obtiene un diagnóstico completo del servicio local y sus proveedores."""
        port_open = self.is_port_in_use()
        healthy = self.is_healthy()

        status_info: Dict[str, Any] = {
            "is_running": healthy or port_open,
            "is_healthy": healthy,
            "port": self.port,
            "base_url": self.base_url,
            "log_path": str(self.log_file),
            "log_file": str(self.log_file),
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "configured_model": self.default_model,
            "default_model": self.default_model,
            "openrouter_configured": bool(self.openrouter_api_key),
            "has_api_key": bool(self.openrouter_api_key),
            "providers_status": {}
        }

        if healthy:
            try:
                admin_status_url = f"{self.base_url}/admin/api/status"
                req = urllib.request.Request(admin_status_url, headers={"User-Agent": "JEV-Monitor/1.0"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        status_info["admin_status"] = {
                            "version": data.get("version"),
                            "active_provider_count": len(data.get("providers", []))
                        }
                        # Extraer estado específico de OpenRouter y locales
                        for p in data.get("providers", []):
                            p_id = p.get("provider_id")
                            if p_id in ("open_router", "ollama", "lmstudio", "gemini", "deepseek"):
                                status_info["providers_status"][p_id] = {
                                    "status": p.get("status"),
                                    "label": p.get("label"),
                                    "kind": p.get("kind")
                                }
            except Exception as e:
                status_info["admin_status_error"] = str(e)

        return status_info

    def start(self, timeout_seconds: float = 12.0) -> Tuple[bool, str]:
        """Inicia el servidor fcc-server en segundo plano si no está corriendo."""
        if self.is_healthy():
            return True, f"FCC Server ya está operativo en {self.base_url}."

        if not self.fcc_server_bin.exists():
            return False, f"No se encontró el binario '{self.fcc_server_bin}'. Ejecute 'uv sync' en tools/free-claude-code."

        # Construcción del entorno con variables seguras
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env["FCC_OPEN_BROWSER"] = "false"  # Evita abrir ventanas automáticas de navegador
        env["PROXY_AUTH_ENABLED"] = "false"
        env["ANTHROPIC_AUTH_TOKEN"] = "freecc"
        if self.openrouter_api_key:
            env["OPENROUTER_API_KEY"] = self.openrouter_api_key
        if self.default_model:
            env["MODEL"] = self.default_model

        # Preparar archivo de log
        out_f = open(self.log_file, "a", encoding="utf-8")
        out_f.write(f"\n--- [JEV]: Iniciando fcc-server en {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        out_f.flush()

        try:
            cmd = [str(self.fcc_server_bin)]
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.repo_dir),
                env=env,
                stdout=out_f,
                stderr=out_f,
                creationflags=creationflags
            )

            # Esperar a que el servidor esté listo
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                if self.is_healthy():
                    return True, f"FCC Server iniciado con éxito en {self.base_url} (PID: {self.process.pid})."
                time.sleep(0.4)

            return False, f"El servidor arrancó (PID: {self.process.pid}) pero no respondió a las comprobaciones de salud en {timeout_seconds}s. Revise '{self.log_file}'."

        except Exception as e:
            return False, f"Error al lanzar el subproceso fcc-server: {str(e)}"

    def stop(self) -> Tuple[bool, str]:
        """Detiene el servidor en segundo plano si fue iniciado por este proceso o libera el puerto."""
        killed = False
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3.0)
                killed = True
            except Exception:
                try:
                    self.process.kill()
                    killed = True
                except Exception:
                    pass

        # Si aún sigue escuchando en Windows, forzar terminación del puerto
        if sys.platform == "win32" and self.is_port_in_use():
            try:
                cmd = f"Get-NetTCPConnection -LocalPort {self.port} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
                subprocess.run(["powershell", "-Command", cmd], capture_output=True, timeout=5)
                killed = True
            except Exception:
                pass

        if killed:
            return True, f"Servidor FCC en puerto {self.port} detenido."
        return True, "No había instancias activas de FCC."

    def ensure_running(self) -> Tuple[bool, str]:
        """Garantiza que el servidor esté activo, iniciándolo si es necesario."""
        if self.is_healthy():
            return True, f"FCC Server activo en {self.base_url}."
        return self.start()

    def sync_openrouter_key(self, api_key: str, model: Optional[str] = None) -> bool:
        """Persiste la clave de OpenRouter tanto en memoria como en los archivos .env del sistema."""
        if not api_key:
            return False

        self.openrouter_api_key = api_key.strip()
        os.environ["OPENROUTER_API_KEY"] = self.openrouter_api_key

        if model:
            self.default_model = model.strip()
            os.environ["FCC_MODEL"] = self.default_model

        # 1. Guardar en .env raíz de JEV
        root_env = self.base_dir / ".env"
        self._upsert_env_file(root_env, {
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "FCC_MODEL": self.default_model,
            "FCC_PORT": str(self.port)
        })

        # 2. Guardar en ~/.fcc/.env (estándar de Free Claude Code)
        user_fcc_env = Path.home() / ".fcc" / ".env"
        user_fcc_env.parent.mkdir(parents=True, exist_ok=True)
        self._upsert_env_file(user_fcc_env, {
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "MODEL": self.default_model,
            "PORT": str(self.port),
            "FCC_OPEN_BROWSER": "false"
        })

        return True

    def update_config(self, openrouter_api_key: Optional[str] = None, default_model: Optional[str] = None) -> bool:
        """Actualiza la configuración en memoria y la persiste en disco."""
        if openrouter_api_key is not None:
            self.openrouter_api_key = openrouter_api_key.strip()
            os.environ["OPENROUTER_API_KEY"] = self.openrouter_api_key
        if default_model is not None:
            self.default_model = default_model.strip()
            os.environ["FCC_MODEL"] = self.default_model

        if openrouter_api_key or default_model:
            return self.sync_openrouter_key(self.openrouter_api_key, self.default_model)
        return True

    @staticmethod
    def _upsert_env_file(path: Path, updates: Dict[str, str]) -> None:
        """Actualiza o añade pares clave=valor en un archivo .env sin destruir comentarios."""
        lines = []
        existing_keys = set()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        k, _ = stripped.split("=", 1)
                        k = k.strip()
                        if k in updates:
                            lines.append(f"{k}={updates[k]}\n")
                            existing_keys.add(k)
                            continue
                    lines.append(line)

        for k, v in updates.items():
            if k not in existing_keys:
                lines.append(f"{k}={v}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
