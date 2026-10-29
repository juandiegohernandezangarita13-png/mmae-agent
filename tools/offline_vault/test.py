"""
Pruebas unitarias para el motor de base de conocimiento offline (OfflineVaultEngine).
"""
import unittest
import tempfile
import os
from pathlib import Path

from vault_engine import OfflineVaultEngine


class TestOfflineVault(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.engine = OfflineVaultEngine(db_path=self.temp_db.name)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_ingest_and_get_document(self):
        doc_id = self.engine.ingest(
            title="Protocolo de Red",
            content="Instrucciones para configurar interfaces y servidores DNS locales.",
            category="networking",
            tags=["dns", "network", "offline"]
        )
        self.assertIsInstance(doc_id, int)

        doc = self.engine.get_document(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["title"], "Protocolo de Red")
        self.assertIn("dns", doc["tags"])
        self.assertIn("configurar interfaces", doc["content"])

    def test_full_text_search(self):
        self.engine.ingest(
            title="Guía de MicroVMs",
            content="smolvm permite arrancar máquinas virtuales en menos de doscientos milisegundos con kernel Linux.",
            category="virtualization",
            tags=["smolvm", "microvm", "sandbox"]
        )
        self.engine.ingest(
            title="Detección WiFi",
            content="Análisis de varianza estadística sobre señales de radiofrecuencia CSI para presencia humana.",
            category="sensing",
            tags=["wifi", "csi", "radar"]
        )

        # Buscar término presente en el primer documento
        results = self.engine.query_vault("microvm")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Guía de MicroVMs")
        self.assertIn("smolvm", results[0]["snippet"])

        # Buscar término presente en el segundo documento
        results2 = self.engine.query_vault("radiofrecuencia")
        self.assertGreaterEqual(len(results2), 1)
        self.assertEqual(results2[0]["title"], "Detección WiFi")

        # Buscar término inexistente
        results_none = self.engine.query_vault("cuantica_espacial_inexistente")
        self.assertEqual(len(results_none), 0)

    def test_stats(self):
        self.engine.ingest(title="Doc 1", content="Texto 1")
        self.engine.ingest(title="Doc 2", content="Texto 2")
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_documents"], 2)


if __name__ == "__main__":
    unittest.main()
