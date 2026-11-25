"""Crypto helpers: password hashing, AES-256-GCM at rest, pseudonyms, JWT."""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config


# ---- passwords (scrypt, stdlib) -------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split("$")
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(dk.hex(), dk_hex)


# ---- encryption at rest (AES-256-GCM) -------------------------------------
def encrypt(plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Return (nonce, ciphertext). `aad` binds the ciphertext to its record id."""
    nonce = os.urandom(12)
    return nonce, AESGCM(config.MASTER_KEY).encrypt(nonce, plaintext, aad)


def decrypt(nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    return AESGCM(config.MASTER_KEY).decrypt(nonce, ciphertext, aad)


# ---- pseudonyms: reviewers never see who wrote a question ------------------
def pseudonym_for(faculty_id: str) -> str:
    mac = hmac.new(config.PSEUDONYM_KEY, faculty_id.encode(), hashlib.sha256).hexdigest()
    return "FAC-" + mac[:12].upper()


# ---- JWT -------------------------------------------------------------------
def create_token(faculty_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_TTL_MINUTES)
    return jwt.encode(
        {"sub": faculty_id, "exp": exp, "jti": uuid.uuid4().hex},
        config.JWT_SECRET,
        algorithm="HS256",
    )


def decode_token(token: str) -> str:
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])["sub"]
