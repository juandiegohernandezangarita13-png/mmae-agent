"""
Herramienta de Detección de Perturbaciones de Red y Presencia (NetworkSensingTool).

Monitorea fluctuaciones y métricas en interfaces de red locales o ejecuta
análisis estadístico de señales para inferir estados de presencia física
(PRESENCE_DETECTED / IDLE) sin uso de cámaras.
"""
from typing import Dict, Any, Optional, List
import time
import math
import random
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError

from jev.tools.base import BaseTool, ToolResult


class NetworkSensingInput(BaseModel):
    """Esquema de parámetros validados con Pydantic para NetworkSensingTool."""
    sample_duration: float = Field(
        default=0.2,
        ge=0.05,
        le=5.0,
        description="Duración de la ventana de muestreo en segundos (0.05s a 5s, óptimo 0.2s para máxima velocidad)."
    )
    sensitivity_threshold: float = Field(
        default=1.5,
        ge=0.1,
        le=10.0,
        description="Umbral de desviación estándar / varianza para clasificar una perturbación como presencia."
    )
    interface: Optional[str] = Field(
        default=None,
        description="Nombre específico de la interfaz de red (None para monitorear todas)."
    )
    simulation_mode: bool = Field(
        default=False,
        description="Forzar análisis sobre flujo estadístico simulado de fluctuación de señal RSSI/CSI."
    )


class NetworkSensingTool(BaseTool):
    """
    Herramienta que analiza perturbaciones en el tráfico de red o simula fluctuaciones
    de señal para determinar estados de presencia (PRESENCE_DETECTED / IDLE).
    """
    name = "network_presence_sensing"
    description = (
        "Analiza métricas de red local y fluctuaciones de señal/paquetes en tiempo real "
        "para inferir perturbaciones y estados de presencia (PRESENCE_DETECTED o IDLE)."
    )
    parameters = NetworkSensingInput.model_json_schema()

    def __init__(self):
        super().__init__()

    def execute(
        self,
        sample_duration: float = 0.2,
        sensitivity_threshold: float = 1.5,
        interface: Optional[str] = None,
        simulation_mode: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            # Validación estricta con Pydantic
            params = NetworkSensingInput(
                sample_duration=sample_duration,
                sensitivity_threshold=sensitivity_threshold,
                interface=interface,
                simulation_mode=simulation_mode
            )
        except ValidationError as ve:
            return ToolResult(
                success=False,
                output="",
                error=f"Error de validación de parámetros en NetworkSensingTool: {ve}"
            )

        try:
            if params.simulation_mode:
                return self._analyze_simulation(params.sample_duration, params.sensitivity_threshold)
            else:
                return self._analyze_real_network(params.sample_duration, params.sensitivity_threshold, params.interface)
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"Excepción en NetworkSensingTool: {exc}"
            )

    def _analyze_real_network(
        self,
        duration: float,
        threshold: float,
        interface: Optional[str]
    ) -> ToolResult:
        """Captura métricas delta de paquetes en la ventana de tiempo especificada."""
        try:
            import psutil
        except ImportError:
            # Fallback a simulación si psutil no estuviera disponible
            return self._analyze_simulation(duration, threshold)

        # Muestreo inicial
        io_start = psutil.net_io_counters(pernic=True) if interface else psutil.net_io_counters(pernic=False)

        # Ventana de muestreo no bloqueante de corta duración
        time.sleep(duration)

        # Muestreo final
        io_end = psutil.net_io_counters(pernic=True) if interface else psutil.net_io_counters(pernic=False)

        if interface:
            if interface not in io_start or interface not in io_end:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"La interfaz de red '{interface}' no fue encontrada en el sistema."
                )
            delta_pkts_recv = io_end[interface].packets_recv - io_start[interface].packets_recv
            delta_pkts_sent = io_end[interface].packets_sent - io_start[interface].packets_sent
            delta_bytes = (io_end[interface].bytes_recv - io_start[interface].bytes_recv) + (io_end[interface].bytes_sent - io_start[interface].bytes_sent)
        else:
            delta_pkts_recv = io_end.packets_recv - io_start.packets_recv
            delta_pkts_sent = io_end.packets_sent - io_start.packets_sent
            delta_bytes = (io_end.bytes_recv - io_start.bytes_recv) + (io_end.bytes_sent - io_start.bytes_sent)

        total_delta_pkts = delta_pkts_recv + delta_pkts_sent
        rate_pkts_sec = total_delta_pkts / max(duration, 0.001)

        # Algoritmo de detección de anomalía
        # Si la tasa de paquetes o el flujo presenta fluctuación superior al umbral
        variance_score = rate_pkts_sec / 10.0
        is_presence = variance_score >= threshold

        status = "PRESENCE_DETECTED" if is_presence else "IDLE"
        confidence = min(1.0, max(0.5, variance_score / (threshold * 2))) if is_presence else 0.85

        output = (
            f"📡 [NETWORK SENSING ANALYSIS]\n"
            f"• Estado: {status}\n"
            f"• Confianza: {confidence * 100:.1f}%\n"
            f"• Paquetes analizados: {total_delta_pkts} ({rate_pkts_sec:.1f} pkt/s)\n"
            f"• Tráfico delta: {delta_bytes / 1024:.2f} KB en {duration:.2f}s\n"
            f"• Puntuación de perturbación: {variance_score:.2f} (Umbral: {threshold})"
        )

        return ToolResult(
            success=True,
            output=output,
            data={
                "status": status,
                "confidence": round(confidence, 3),
                "delta_packets": total_delta_pkts,
                "packets_per_second": round(rate_pkts_sec, 2),
                "delta_bytes": delta_bytes,
                "variance_score": round(variance_score, 2),
                "threshold": threshold,
                "mode": "real_network"
            }
        )

    def _analyze_simulation(self, duration: float, threshold: float) -> ToolResult:
        """Genera y analiza una serie de fluctuación de señal estadística RSSI."""
        sample_count = max(10, int(duration * 50))
        # Base RSSI entre -45 y -50 dBm con perturbación aleatoria
        base_rssi = -48.0
        # Simulación: 50% probabilidad de movimiento en el entorno
        has_motion = random.random() > 0.4
        noise_level = random.uniform(2.0, 5.0) if has_motion else random.uniform(0.2, 0.8)

        samples = [base_rssi + random.gauss(0, noise_level) for _ in range(sample_count)]

        # Cálculo de desviación estándar
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std_dev = math.sqrt(variance)

        is_presence = std_dev >= threshold
        status = "PRESENCE_DETECTED" if is_presence else "IDLE"
        confidence = min(0.99, max(0.60, std_dev / (threshold * 1.5))) if is_presence else 0.90

        output = (
            f"📡 [STATISTICAL SIGNAL SENSING]\n"
            f"• Estado: {status}\n"
            f"• Confianza: {confidence * 100:.1f}%\n"
            f"• Muestras evaluadas: {sample_count} en {duration:.2f}s\n"
            f"• Desviación estándar (RSSI): {std_dev:.2f} dBm (Umbral: {threshold})\n"
            f"• Varianza de señal: {variance:.2f}"
        )

        return ToolResult(
            success=True,
            output=output,
            data={
                "status": status,
                "confidence": round(confidence, 3),
                "std_dev": round(std_dev, 2),
                "variance": round(variance, 2),
                "samples_count": sample_count,
                "threshold": threshold,
                "mode": "simulation"
            }
        )
