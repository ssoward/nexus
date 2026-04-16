import base64
import hashlib
import os

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_derived_key: bytes | None = None


def init_crypto(app_secret: str, crypto_salt: str) -> None:
    global _derived_key
    key = hashlib.pbkdf2_hmac(
        "sha256",
        app_secret.encode(),
        crypto_salt.encode(),
        600_000,
        dklen=32,
    )
    _derived_key = key


def _get_key() -> bytes:
    if _derived_key is None:
        raise RuntimeError("Crypto not initialized — call init_crypto() first")
    return _derived_key


def encrypt_totp_secret(totp_secret: str, user_id: int) -> bytes:
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(12)
    plaintext = totp_secret.encode()
    associated_data = str(user_id).encode()
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce + ciphertext


def decrypt_totp_secret(encrypted: bytes, user_id: int) -> str:
    aesgcm = AESGCM(_get_key())
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    associated_data = str(user_id).encode()
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
    return plaintext.decode()


def _pw_digest(password: str) -> bytes:
    """SHA-256 → base64 so bcrypt sees 44 printable bytes (full 256-bit entropy)."""
    return base64.b64encode(hashlib.sha256(password.encode()).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_digest(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_pw_digest(plain), hashed.encode())


def generate_secret_hex(nbytes: int = 32) -> str:
    return os.urandom(nbytes).hex()
