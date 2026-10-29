"""
Pruebas unitarias para el módulo de WiFi Sensing / Detección de Presencia.
"""
import unittest
import sys
from pathlib import Path

# Agregar el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))
from analyzer import WifiSignalAnalyzer, simulate_environment


class TestWifiSensing(unittest.TestCase):
    def setUp(self):
        self.analyzer = WifiSignalAnalyzer(variance_threshold=3.0)

    def test_static_room_no_motion(self):
        # Serie de lecturas estables (varianza mínima)
        static_series = [-60.1, -60.2, -60.0, -60.1, -60.3, -60.1, -60.2, -60.0]
        res = self.analyzer.detect_presence(static_series)
        self.assertEqual(res["status"], "NO_MOTION")
        self.assertGreater(res["confidence"], 60.0)
        self.assertLess(res["variance"], 1.0)

    def test_motion_presence_detected(self):
        # Serie de lecturas con perturbaciones agudas causadas por movimiento físico
        motion_series = [-60.0, -54.2, -67.1, -58.0, -52.4, -66.3, -59.1, -51.0]
        res = self.analyzer.detect_presence(motion_series)
        self.assertEqual(res["status"], "PRESENCE_DETECTED")
        self.assertGreater(res["confidence"], 50.0)
        self.assertGreater(res["variance"], 3.0)

    def test_insufficient_samples(self):
        res = self.analyzer.detect_presence([-60.0])
        self.assertEqual(res["status"], "INSUFFICIENT_DATA")

    def test_synthetic_generators(self):
        sim_motion = simulate_environment("motion")
        self.assertEqual(len(sim_motion), 15)
        res_motion = self.analyzer.detect_presence(sim_motion)
        self.assertIn(res_motion["status"], ["PRESENCE_DETECTED", "NO_MOTION"])


if __name__ == "__main__":
    unittest.main()
