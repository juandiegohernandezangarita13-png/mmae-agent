"""
Pruebas unitarias para el asistente de ingeniería inversa (ReverseEngineeringAssistant).
"""
import unittest
import tempfile
import os
from pathlib import Path

from decompiler_helper import ReverseEngineeringAssistant


class TestReverseEngineering(unittest.TestCase):
    def setUp(self):
        # Crear archivo de prueba con contenido conocido
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
        self.temp_file.write("""
import subprocess
import requests

def fetch_data():
    url = "https://example.com/api/data"
    res = requests.get(url)
    return res.text

def run_cmd():
    subprocess.run(["cmd.exe", "/c", "dir"])
""")
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_metadata_and_format(self):
        assistant = ReverseEngineeringAssistant(self.temp_file.name)
        fmt = assistant.identify_format()
        self.assertEqual(fmt, "Python Script (.py)")
        entropy = assistant.calculate_entropy()
        self.assertGreater(entropy, 1.0)
        self.assertLess(entropy, 8.0)

    def test_extract_strings_and_indicators(self):
        assistant = ReverseEngineeringAssistant(self.temp_file.name)
        strings_list = assistant.extract_strings(min_len=4)
        self.assertTrue(any("https://example.com/api/data" in s for s in strings_list))
        self.assertTrue(any("subprocess" in s for s in strings_list))

        indicators = assistant.analyze_indicators(strings_list)
        self.assertTrue(any("https://example.com/api/data" in item for item in indicators["network"]))
        self.assertTrue(any("subprocess" in item or "cmd.exe" in item for item in indicators["system_execution"]))

    def test_generate_report(self):
        assistant = ReverseEngineeringAssistant(self.temp_file.name)
        report = assistant.generate_report()
        self.assertIn("# Reporte de Ingeniería Inversa (REA)", report)
        self.assertIn("Metadatos del Archivo", report)
        self.assertIn("Nivel de Riesgo", report)


if __name__ == "__main__":
    unittest.main()
