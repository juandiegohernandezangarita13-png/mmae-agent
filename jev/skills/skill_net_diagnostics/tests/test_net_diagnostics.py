"""
Pruebas unitarias para skill_net_diagnostics.
"""
import unittest
from jev.skills.skill_net_diagnostics.handler import handle, dns_resolve, tcp_ping


class TestSkillNetDiagnostics(unittest.TestCase):

    def test_01_dns_resolve_localhost(self):
        res = dns_resolve("localhost")
        self.assertTrue(res["success"])
        self.assertIn("127.0.0.1", res["resolved_ips"])
        self.assertGreater(res["lookup_time_ms"], 0.0)

    def test_02_dns_resolve_invalid_domain(self):
        res = dns_resolve("invalid-nonexistent-domain-12345.xyz")
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    def test_03_tcp_ping_localhost(self):
        res = tcp_ping("127.0.0.1", port=80, timeout=0.5, count=1)
        self.assertIn("packet_loss_pct", res)
        self.assertIn("sent", res)

    def test_04_handle_wrapper(self):
        res = handle(action="dns_resolve", target="127.0.0.1")
        self.assertTrue(res["success"])


if __name__ == "__main__":
    unittest.main()
