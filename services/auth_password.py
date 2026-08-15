"""Password hashing via bcrypt."""
from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("password must be at least 8 chars")
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False
