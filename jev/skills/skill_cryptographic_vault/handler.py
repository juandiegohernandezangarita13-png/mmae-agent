"""
Handler para skill_cryptographic_vault.
Bóveda criptográfica y de integridad local basada en stdlib hashlib / hmac.
"""
from typing import Dict, Any
import hashlib
import hmac
import secrets

def handle(**kwargs) -> Dict[str, Any]:
    action = kwargs.get("action", "generate_hash")
    data_str = kwargs.get("data", "")
    secret = kwargs.get("secret_key", "")

    if action == "generate_hash":
        digest = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        return {
            "status": "success",
            "algorithm": "SHA-256",
            "hash": digest
        }
    elif action == "generate_hmac":
        if not secret:
            secret = secrets.token_hex(16)
        mac = hmac.new(secret.encode("utf-8"), data_str.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "status": "success",
            "algorithm": "HMAC-SHA256",
            "hmac": mac,
            "secret_used": secret
        }
    elif action == "derive_key":
        salt = kwargs.get("salt") or secrets.token_bytes(16)
        if isinstance(salt, str):
            salt = salt.encode("utf-8")
        derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100000)
        return {
            "status": "success",
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": 100000,
            "derived_key_hex": derived.hex()
        }
    return {"status": "error", "error": f"Acción desconocida '{action}'"}
