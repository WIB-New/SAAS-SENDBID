"""
StorageHub — Chiffrement AES-256 au repos (Fernet / AES-128-CBC + HMAC-SHA256)
Les fichiers KYC et reçus sont chiffrés avant d'être écrits sur le disque.
La clé est dérivée via PBKDF2 depuis ENCRYPTION_KEY dans les variables d'environnement.
"""
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import HTTPException

SENSITIVE_CATEGORIES = {"kyc", "receipts"}
_SALT = b"storagehub_static_salt_v1"   # Salt fixe — rotation de clé = re-chiffrement manuel


def _get_fernet() -> Fernet:
    """Derive une clé Fernet depuis settings.encryption_key via PBKDF2-SHA256."""
    from app.config import settings
    raw = settings.encryption_key.encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=390000)
    key = base64.urlsafe_b64encode(kdf.derive(raw))
    return Fernet(key)


def should_encrypt(category: str) -> bool:
    return category in SENSITIVE_CATEGORIES


def encrypt_bytes(content: bytes, category: str) -> bytes:
    """Chiffre le contenu si la catégorie est sensible. Retourne les bytes inchangés sinon."""
    if not should_encrypt(category):
        return content
    return _get_fernet().encrypt(content)


def decrypt_bytes(content: bytes, category: str) -> bytes:
    """Déchiffre le contenu si la catégorie est sensible."""
    if not should_encrypt(category):
        return content
    try:
        return _get_fernet().decrypt(content)
    except (InvalidToken, Exception) as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")
