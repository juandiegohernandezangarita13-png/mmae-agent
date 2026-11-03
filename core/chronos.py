"""
Módulo Chronos: Percepción del tiempo, telemetría y medición de inactividad de usuario.
Proporciona medición precisa del tiempo de inactividad del usuario en Windows mediante Win32 API,
así como temporizadores de ejecución con soporte para context managers y decoradores.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypeVar, cast

# Intentar importar win32api si está disponible
try:
    import win32api
    _HAS_WIN32API = True
except ImportError:
    win32api = None  # type: ignore
    _HAS_WIN32API = False


class LASTINPUTINFO(ctypes.Structure):
    """Estructura Win32 LASTINPUTINFO para ctypes."""
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class Chronos:
    """
    Sensor temporal del sistema operativo y telemetría de interacción de usuario en Windows.
    Permite detectar inactividad del usuario para activar bucles de curiosidad u optimizaciones de fondo.
    """

    @staticmethod
    def get_user_idle_seconds() -> float:
        """
        Obtiene los segundos transcurridos desde la última interacción de entrada (teclado/ratón)
        del usuario en Windows utilizando win32api.GetLastInputInfo o ctypes.
        """
        if sys.platform != "win32":
            # Fallback en entornos no-Windows (desarrollo o testing)
            return 0.0

        try:
            if _HAS_WIN32API and win32api is not None:
                last_input_tick = win32api.GetLastInputInfo()
                current_tick = win32api.GetTickCount()
                # Manejar desbordamiento de 32 bits en GetTickCount (~49.7 días)
                idle_ms = (current_tick - last_input_tick) & 0xFFFFFFFF
                return float(idle_ms) / 1000.0
        except Exception:
            pass

        # Fallback de alta fidelidad vía ctypes directo a user32.dll
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if user32.GetLastInputInfo(ctypes.byref(lii)):
                current_tick = kernel32.GetTickCount()
                idle_ms = (current_tick - lii.dwTime) & 0xFFFFFFFF
                return float(idle_ms) / 1000.0
        except Exception:
            pass

        return 0.0

    @classmethod
    def is_user_idle(cls, threshold_seconds: float = 900.0) -> bool:
        """
        Indica si el usuario lleva inactivo más tiempo que el umbral configurado (por defecto 900s = 15m).
        """
        return cls.get_user_idle_seconds() >= threshold_seconds

    @staticmethod
    def get_system_uptime_seconds() -> float:
        """Retorna el tiempo de actividad del sistema operativo en segundos."""
        if sys.platform == "win32":
            try:
                # GetTickCount64 evita el reinicio de los 49.7 días
                kernel32 = ctypes.windll.kernel32
                if hasattr(kernel32, "GetTickCount64"):
                    return float(kernel32.GetTickCount64()) / 1000.0
                if _HAS_WIN32API and win32api is not None:
                    return float(win32api.GetTickCount()) / 1000.0
            except Exception:
                pass
        return time.monotonic()

    @staticmethod
    def now_utc_iso() -> str:
        """Retorna la marca temporal actual en formato ISO 8601 UTC."""
        return datetime.now(timezone.utc).isoformat()


F = TypeVar("F", bound=Callable[..., Any])


class ExecutionTimer:
    """
    Context manager y decorador de telemetría para medir con precisión sub-milisegundo
    la duración de ejecución de herramientas, scripts y subprocesos CLI.
    """

    def __init__(
        self,
        name: str = "execution_task",
        metadata: Optional[Dict[str, Any]] = None,
        on_finish: Optional[Callable[[ExecutionTimer], None]] = None,
    ) -> None:
        self.name: str = name
        self.metadata: Dict[str, Any] = metadata or {}
        self.on_finish: Optional[Callable[[ExecutionTimer], None]] = on_finish

        self.start_perf: float = 0.0
        self.end_perf: float = 0.0
        self.start_time_iso: str = ""
        self.end_time_iso: str = ""
        self.duration_seconds: float = 0.0
        self.success: bool = False
        self.error: Optional[str] = None

    def __enter__(self) -> ExecutionTimer:
        self.start_time_iso = Chronos.now_utc_iso()
        self.start_perf = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        self.end_perf = time.perf_counter()
        self.end_time_iso = Chronos.now_utc_iso()
        self.duration_seconds = max(0.0, self.end_perf - self.start_perf)

        if exc_type is None:
            self.success = True
            self.error = None
        else:
            self.success = False
            self.error = f"{exc_type.__name__}: {str(exc_val)}"

        if self.on_finish:
            try:
                self.on_finish(self)
            except Exception:
                pass

        # No suprimir la excepción si ocurrió
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serializa la métrica de ejecución en un diccionario."""
        return {
            "name": self.name,
            "duration_seconds": round(self.duration_seconds, 4),
            "duration_ms": round(self.duration_seconds * 1000.0, 2),
            "success": self.success,
            "error": self.error,
            "start_time": self.start_time_iso,
            "end_time": self.end_time_iso,
            "metadata": self.metadata,
        }

    @classmethod
    def measure(
        cls,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Callable[[F], F]:
        """
        Decorador para instrumentar funciones síncronas con medición de tiempo.
        """
        def decorator(func: F) -> F:
            timer_name = name or func.__name__

            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with cls(name=timer_name, metadata=metadata):
                    return func(*args, **kwargs)

            return cast(F, wrapper)

        return decorator


__all__ = ["Chronos", "ExecutionTimer"]
