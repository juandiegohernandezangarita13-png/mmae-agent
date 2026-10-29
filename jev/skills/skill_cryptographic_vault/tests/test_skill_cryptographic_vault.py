"""
Tests unitarios para skill_cryptographic_vault.
"""
import unittest
import handler

class TestCryptoVault(unittest.TestCase):
    def test_sha256_generation(self):
        res = handler.handle(action="generate_hash", data="JEV Secure Token")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(len(res.get("hash")), 64)

    def test_hmac_generation(self):
        res = handler.handle(action="generate_hmac", data="payload_data", secret_key="super_secret")
        self.assertEqual(res.get("status"), "success")
        self.assertIn("hmac", res)

if __name__ == "__main__":
    unittest.main()
