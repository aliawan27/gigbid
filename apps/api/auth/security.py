"""Multi-user auth: PBKDF2 password hashes + HMAC-signed bearer session tokens; Fernet-encrypted OAuth tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException

SECRET = os.getenv("APP_SECRET_KEY", "dev-secret-change-me").encode()


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    salt_b64, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(pw, base64.b64decode(salt_b64)), stored)


def make_token(user_id: str, ttl: int = 7 * 86400) -> str:
    exp = str(int(time.time()) + ttl)
    sig = hmac.new(SECRET, f"{user_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{exp}.{sig}"


def read_token(token: str) -> str | None:
    try:
        user_id, exp, sig = token.rsplit(".", 2)
    except ValueError:
        return None
    good = hmac.new(SECRET, f"{user_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig) or int(exp) < time.time():
        return None
    return user_id


def current_user(authorization: str = Header(default="")) -> str:
    uid = read_token(authorization.removeprefix("Bearer ").strip()) if authorization else None
    if not uid:
        raise HTTPException(401, "not signed in")
    return uid


def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET + b"oauth").digest())
    return Fernet(key)


def encrypt_token(tok: str) -> str:
    return _fernet().encrypt(tok.encode()).decode()


def decrypt_token(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()
