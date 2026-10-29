"""
Módulo de Detección de Presencia y Movimiento por Variación de Señal WiFi (CSI / RSSI).
Analiza perturbaciones de radiofrecuencia (multi-path fading y fluctuación de señal)
para inferir presencia humana sin necesidad de cámaras.
"""
from typing import List, Dict, Any, Optional, Tuple
import subprocess
import math
import time
import re
import json
import argparse


class WifiSignalAnalyzer:
    """
    Analizador estadístico de perturbaciones en señales WiFi para detección de presencia.
    Utiliza ventanas de media móvil y desviación estándar para detectar anomalías
    producidas por el movimiento de cuerpos en el campo electromagnético.
    """

    def __init__(self, variance_threshold: float = 3.5, window_size: int = 10):
        self.variance_threshold = variance_threshold
        self.window_size = window_size

    def calculate_statistics(self, samples: List[float]) -> Dict[str, float]:
        """Calcula media, varianza y desviación estándar de una serie de muestras."""
        if not samples:
            return {"mean": 0.0, "variance": 0.0, "std_dev": 0.0}

        n = len(samples)
        mean = sum(samples) / n
        variance = sum((x - mean) ** 2 for x in samples) / (n if n == 1 else n - 1)
        std_dev = math.sqrt(variance)

        return {
            "mean": round(mean, 2),
            "variance": round(variance, 4),
            "std_dev": round(std_dev, 4)
        }

    def detect_presence(self, signal_series: List[float]) -> Dict[str, Any]:
        """
        Analiza una serie temporal de muestras de señal (RSSI en dBm o amplitudes CSI).
        Devuelve el estado de presencia y el porcentaje de confianza.
        """
        if len(signal_series) < 3:
            return {
                "status": "INSUFFICIENT_DATA",
                "confidence": 0.0,
                "variance": 0.0,
                "mean_signal": 0.0,
                "details": "Se requieren al menos 3 muestras para un análisis confiable."
            }

        stats = self.calculate_statistics(signal_series)
        variance = stats["variance"]
        std_dev = stats["std_dev"]

        # Si la varianza excede el umbral, indica perturbación física en el entorno
        if variance >= self.variance_threshold:
            # Calcular confianza en función de cuánto excede el umbral (cap a 99%)
            ratio = variance / self.variance_threshold
            confidence = min(99.0, round(50.0 + (ratio * 15.0), 2))
            status = "PRESENCE_DETECTED"
            details = f"Perturbación detectada en la señal WiFi (Varianza: {variance} > {self.variance_threshold})."
        else:
            # Si la varianza es muy baja, es señal estacionaria (ambiente vacío)
            quietness = max(0.1, self.variance_threshold - variance)
            confidence = min(99.0, round(60.0 + (quietness * 10.0), 2))
            status = "NO_MOTION"
            details = f"Señal de radio estable. No se detectan perturbaciones (Varianza: {variance})."

        return {
            "status": status,
            "confidence": confidence,
            "variance": variance,
            "std_dev": std_dev,
            "mean_signal": stats["mean"],
            "samples_count": len(signal_series),
            "details": details
        }

    @staticmethod
    def get_live_wifi_rssi() -> Optional[float]:
        """
        Intenta leer el nivel de señal (calidad o RSSI) de la interfaz WiFi actual en Windows.
        Retorna el valor en dBm o porcentaje relativo (-100 a -30 dBm).
        """
        try:
            cmd = ["netsh", "wlan", "show", "interfaces"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, encoding="utf-8", errors="ignore")
            if res.returncode == 0:
                match = re.search(r"(?:Señal|Signal)\s*:\s*(\d+)%", res.stdout)
                if match:
                    pct = float(match.group(1))
                    # Convertir porcentaje (0-100) a RSSI aproximado en dBm (-100 dBm a -50 dBm)
                    rssi_approx = (pct / 2.0) - 100.0
                    return rssi_approx
        except Exception:
            pass
        return None

    def analyze_live(self, num_samples: int = 10, interval_seconds: float = 0.3) -> Dict[str, Any]:
        """Captura muestras en vivo de la tarjeta de red WiFi y determina si hay presencia."""
        samples = []
        for _ in range(num_samples):
            val = self.get_live_wifi_rssi()
            if val is not None:
                samples.append(val)
            time.sleep(interval_seconds)

        if not samples:
            # Si no hay adaptador WiFi activo o no hay conexión, generar simulación informada
            return {
                "status": "HARDWARE_UNAVAILABLE",
                "confidence": 0.0,
                "variance": 0.0,
                "mean_signal": 0.0,
                "details": "No se detectó interfaz WiFi conectada en netsh wlan. Use el modo sintético."
            }

        return self.detect_presence(samples)


def simulate_environment(scenario: str = "motion") -> List[float]:
    """Genera datos sintéticos para validación de algoritmos CSI/RSSI."""
    import random
    base_rssi = -60.0
    samples = []
    if scenario == "motion":
        # Simula persona caminando entre emisor y receptor (fluctuaciones fuertes de +/- 5 dBm)
        for i in range(15):
            noise = random.gauss(0, 3.2)
            samples.append(round(base_rssi + noise, 2))
    else:
        # Habitación vacía (señal estable con ruido térmico mínimo de +/- 0.4 dBm)
        for i in range(15):
            noise = random.gauss(0, 0.3)
            samples.append(round(base_rssi + noise, 2))
    return samples


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WiFi CSI & Presence Sensing Analyzer")
    parser.add_argument("--mode", choices=["live", "simulate"], default="simulate", help="Modo de ejecución")
    parser.add_argument("--scenario", choices=["motion", "static"], default="motion", help="Escenario de simulación")
    parser.add_argument("--threshold", type=float, default=3.5, help="Umbral de varianza para detección")
    args = parser.parse_args()

    analyzer = WifiSignalAnalyzer(variance_threshold=args.threshold)
    if args.mode == "live":
        print("[*] Capturando señales de interfaz WiFi en vivo...")
        result = analyzer.analyze_live(num_samples=10, interval_seconds=0.2)
    else:
        data = simulate_environment(scenario=args.scenario)
        result = analyzer.detect_presence(data)

    print(json.dumps(result, indent=2))
