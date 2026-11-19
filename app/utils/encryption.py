"""
StorageHub — Chiffrement au repos AES-256-GCM
Les fichiers KYC et reçus sont chiffrés avant d'être écrits sur le disque.

Chaque tenant possède une clé distincte, dérivée par PBKDF2-SHA256 depuis
ENCRYPTION_KEY + un sel propre au tenant — la compromission d'une clé
n'expose qu'un seul client.

Format v2 : b"SH2G" + nonce(12 o) + ciphertext|tag   (AES-256-GCM authentifié)
Format v1 (legacy, lecture seule) : token Fernet à sel statique.
"""
import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import HTTPException

SENSITIVE_CATEGORIES = {"kyc", "receipts"}

V2_MAGIC = b"SH2G"                       # Marqueur de format AES-256-GCM
_NONCE_LEN = 12
_FERNET_TOKEN_PREFIX = b"gAAAAA"         # Préfixe base64 des tokens Fernet
_LEGACY_SALT = b"storagehub_static_salt_v1"  # v1 — conservé pour lire les anciens fichiers


def should_encrypt(category: str) -> bool:
    return category in SENSITIVE_CATEGORIES


def _derive_aes_key(tenant: Optional[str]) -> bytes:
    """Dérive une clé AES-256 propre au tenant depuis ENCRYPTION_KEY."""
    from app.config import settings
    scope = tenant or "internal"
    salt = hashlib.sha256(f"storagehub:enc:v2:{scope}".encode()).digest()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return kdf.derive(settings.encryption_key.encode())


def _legacy_fernet() -> Fernet:
    """Ancienne dérivation v1 (sel statique) — lecture seule, pour migration."""
    from app.config import settings
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=_LEGACY_SALT, iterations=390_000
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.encryption_key.encode()))
    return Fernet(key)


def looks_encrypted(data: bytes) -> bool:
    """True si les bytes ressemblent à un blob chiffré (v2 ou legacy v1)."""
    return data.startswith(V2_MAGIC) or data.startswith(_FERNET_TOKEN_PREFIX)


def encrypt_bytes(content: bytes, category: str, tenant: Optional[str] = None) -> bytes:
    """Chiffre le contenu si la catégorie est sensible (AES-256-GCM, clé par tenant).
    Retourne les bytes inchangés sinon."""
    if not should_encrypt(category):
        return content
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_derive_aes_key(tenant)).encrypt(nonce, content, None)
    return V2_MAGIC + nonce + ciphertext


def decrypt_bytes(content: bytes, category: str, tenant: Optional[str] = None) -> bytes:
    """Déchiffre le contenu — accepte le format v2 (AES-GCM) et v1 (Fernet legacy)."""
    if not should_encrypt(category):
        return content
    try:
        if content.startswith(V2_MAGIC):
            start = len(V2_MAGIC)
            nonce = content[start:start + _NONCE_LEN]
            ciphertext = content[start + _NONCE_LEN:]
            return AESGCM(_derive_aes_key(tenant)).decrypt(nonce, ciphertext, None)
        if content.startswith(_FERNET_TOKEN_PREFIX):
            return _legacy_fernet().decrypt(content)
        # Fichier écrit avant l'introduction du chiffrement : retourner tel quel.
        return content
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")
