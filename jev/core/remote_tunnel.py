"""
Gestor del Túnel Seguro de Cloudflare para Acceso Remoto Móvil a Bable.
Permite conectar con el agente desde el teléfono (Safari/Chrome) desde cualquier lugar
(WiFi, 4G, 5G) sin abrir puertos ni configurar routers.
"""
import os
import sys
import re
import time
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any


class CloudflareTunnelManager:
    _instance: Optional["CloudflareTunnelManager"] = None
    _proc: Optional[subprocess.Popen] = None
    _url: Optional[str] = None
    _lock = threading.Lock()
    _monitor_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "CloudflareTunnelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_binary_path(self) -> Path:
        base_dir = Path(__file__).resolve().parents[2]
        candidates = [
            base_dir / "bin" / "cloudflared.exe",
            Path("bin/cloudflared.exe").resolve(),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "cloudflared.exe"
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]

    def start_tunnel(self, port: int = 8765, timeout: float = 25.0) -> Dict[str, Any]:
        with self._lock:
            # Si ya está activo y vivo, retornar la URL actual
            if self._proc is not None and self._proc.poll() is None and self._url:
                return {
                    "success": True,
                    "url": self._url,
                    "already_running": True,
                    "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={self._url}"
                }

            bin_path = self.get_binary_path()
            if not bin_path.exists():
                return {
                    "success": False,
                    "error": f"No se encontró el ejecutable cloudflared.exe en {bin_path}."
                }

            # Iniciar proceso cloudflared tunnel
            cmd = [str(bin_path), "tunnel", "--url", f"http://127.0.0.1:{port}"]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
            except Exception as e:
                return {"success": False, "error": f"Error iniciando proceso cloudflared: {e}"}

            pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")
            start_time = time.time()
            discovered_url = None

            # Leer la salida hasta capturar la URL pública de Cloudflare
            while time.time() - start_time < timeout:
                if self._proc.poll() is not None:
                    break
                line = self._proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                match = pattern.search(line)
                if match:
                    discovered_url = match.group(0)
                    break

            if discovered_url:
                self._url = discovered_url
                # Hilo supervisor para mantener el proceso vivo
                def _drain_output():
                    try:
                        while self._proc and self._proc.poll() is None:
                            line = self._proc.stdout.readline()
                            if not line:
                                time.sleep(0.2)
                    except Exception:
                        pass
                self._monitor_thread = threading.Thread(target=_drain_output, daemon=True)
                self._monitor_thread.start()

                return {
                    "success": True,
                    "url": self._url,
                    "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={self._url}",
                    "message": "Túnel HTTPS seguro activo"
                }
            else:
                self.stop_tunnel()
                return {
                    "success": False,
                    "error": "Tiempo de espera agotado buscando URL del túnel en Cloudflare."
                }

    def stop_tunnel(self) -> Dict[str, Any]:
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None
            self._url = None
            return {"success": True, "message": "Túnel detenido"}

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            is_alive = self._proc is not None and self._proc.poll() is None
            if not is_alive:
                self._proc = None
                self._url = None
            return {
                "active": bool(is_alive and self._url),
                "url": self._url if is_alive else None,
                "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={self._url}" if is_alive and self._url else None
            }
