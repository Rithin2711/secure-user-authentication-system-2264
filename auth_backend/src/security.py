"""
Security utilities: password hashing and JWT generation.

Required env vars:
- JWT_SECRET: Secret key used to sign JWT tokens (must be set securely).
- JWT_ALGORITHM: (optional) defaults to HS256.
- JWT_EXPIRES_SECONDS: (optional) defaults to 3600.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _jwt_settings() -> tuple[str, str, int]:
    """Load JWT configuration from environment variables.

    In preview/dev environments, `JWT_SECRET` may not be provisioned. To keep the
    service from crashing (and to allow basic signup/login flows), we fall back
    to a deterministic, insecure development secret when JWT_SECRET is missing.

    IMPORTANT: This fallback MUST NOT be used in production. Production should
    always set JWT_SECRET to a strong random value.
    """
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Insecure fallback for preview/dev to avoid hard startup/runtime failures.
        # Orchestrator should set JWT_SECRET for any real environment.
        secret = "insecure-preview-jwt-secret-change-me"

    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    expires_seconds_str = os.getenv("JWT_EXPIRES_SECONDS", "3600")
    try:
        expires_seconds = int(expires_seconds_str)
    except ValueError as exc:
        raise RuntimeError("JWT_EXPIRES_SECONDS must be an integer.") from exc
    return secret, algorithm, expires_seconds


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return pwd_context.verify(plain_password, password_hash)


# PUBLIC_INTERFACE
def create_access_token(subject: str, extra_claims: Dict[str, Any] | None = None) -> str:
    """Create a signed JWT access token.

    Args:
        subject: Subject claim (typically user id or email).
        extra_claims: Optional additional claims to embed in token.

    Returns:
        Encoded JWT token string.
    """
    secret, algorithm, expires_seconds = _jwt_settings()

    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)
