from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from ..domain.errors import AuthError


@dataclass
class Pbkdf2PasswordHasher:
    iterations: int = 200_000

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, self.iterations,
        )
        return f"pbkdf2-sha256${self.iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            algorithm, iterations_raw, salt_hex, digest_hex = password_hash.split("$")
        except ValueError:
            return False
        if algorithm != "pbkdf2-sha256":
            return False
        try:
            iterations = int(iterations_raw)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except ValueError:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations,
        )
        return hmac.compare_digest(candidate, expected)


@dataclass
class JwtTokenService:
    secret: str
    expires_minutes: int = 1440

    def issue(self, user_id: int) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=self.expires_minutes),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def parse(self, token: str) -> int:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            return int(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise AuthError("invalid or expired token")
