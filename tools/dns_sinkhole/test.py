"""
Pruebas unitarias para el DNS Sinkhole y filtro de publicidad (DnsSinkhole).
"""
import unittest
import tempfile
import os
import socket
import struct
from pathlib import Path

from dns_filter import DnsSinkhole


class TestDnsSinkhole(unittest.TestCase):
    def setUp(self):
        self.sinkhole = DnsSinkhole()
        self.sinkhole.add_domains(["adservice.google.com", "doubleclick.net", "telemetry.evil.com"])

    def test_domain_blocking_logic(self):
        # Dominio exacto bloqueado
        self.assertTrue(self.sinkhole.is_blocked("doubleclick.net"))
        self.assertTrue(self.sinkhole.is_blocked("adservice.google.com"))

        # Subdominio de dominio bloqueado
        self.assertTrue(self.sinkhole.is_blocked("sub.doubleclick.net"))
        self.assertTrue(self.sinkhole.is_blocked("tracker.adservice.google.com"))

        # Dominio limpio permitido
        self.assertFalse(self.sinkhole.is_blocked("wikipedia.org"))
        self.assertFalse(self.sinkhole.is_blocked("github.com"))
        self.assertFalse(self.sinkhole.is_blocked("google.com"))

    def test_load_blocklist_file(self):
        temp_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
        temp_file.write("""
# Comentarios de lista hosts
0.0.0.0 malicious-ad.org
127.0.0.1 tracker.analytics.io
plain-bad-domain.com
localhost
""")
        temp_file.close()

        try:
            count = self.sinkhole.load_blocklist_from_file(temp_file.name)
            self.assertEqual(count, 3)
            self.assertTrue(self.sinkhole.is_blocked("malicious-ad.org"))
            self.assertTrue(self.sinkhole.is_blocked("tracker.analytics.io"))
            self.assertTrue(self.sinkhole.is_blocked("plain-bad-domain.com"))
        finally:
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)

    def test_build_sinkhole_dns_response(self):
        # Crear un paquete de consulta DNS estándar para 'doubleclick.net'
        # Transaction ID: 0x1234, Flags: standard query (0x0100)
        query = (
            b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x0bdoubleclick\x03net\x00"  # QNAME
            b"\x00\x01\x00\x01"            # QTYPE=A, QCLASS=IN
        )

        resp = self.sinkhole.build_sinkhole_response(query, "doubleclick.net", sinkhole_ip="0.0.0.0")
        self.assertGreater(len(resp), 12)
        # Verificar que el Transaction ID coincida
        self.assertEqual(resp[:2], b"\x12\x34")
        # Verificar que la respuesta contenga los 4 bytes de IP 0.0.0.0 al final
        self.assertEqual(resp[-4:], socket.inet_aton("0.0.0.0"))

    def test_stats_tracking(self):
        query = (
            b"\xab\xcd\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x0bdoubleclick\x03net\x00"
            b"\x00\x01\x00\x01"
        )
        self.sinkhole.handle_dns_query(query)
        stats = self.sinkhole.get_stats()
        self.assertEqual(stats["total_queries"], 1)
        self.assertEqual(stats["blocked_queries"], 1)
        self.assertEqual(stats["block_rate_percentage"], 100.0)


if __name__ == "__main__":
    unittest.main()
