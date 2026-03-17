"""
Database configuration and session management.

Uses SQLAlchemy with a synchronous PostgreSQL driver. The database connection
details are provided via environment variables.

Supported env var formats:
- Preferred single-URL style:
  - DATABASE_URL (common)
  - POSTGRES_URL (existing template)
  - PGDATABASE_URL (optional)

- Component style (host/port/user/password/db):
  - POSTGRES_HOST / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
  - PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE

Notes:
- The work item for this repository uses a Postgres container whose connection
  string typically looks like: `postgresql://user:pass@host:port/db`.
- This backend uses `psycopg2`, so composed URLs use `postgresql+psycopg2://...`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Generator

from fastapi import HTTPException, status
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _env_first(*keys: str) -> str | None:
    """Return the first environment variable value found among keys."""
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None


def _build_database_url() -> str:
    """Build a PostgreSQL connection URL from environment variables.

    This project runs in multi-container preview environments where:
    - The database may be exposed via a platform-provided POSTGRES_URL string.
    - The URL may point to localhost (valid only from within the DB container),
      while the backend must reach the DB over the container network.
    - The platform may expose the DB to the outside world on a different port than
      the internal Postgres port. The backend must use the *internal* port.

    To keep preview setups robust, we:
    1) Prefer a single URL env var (DATABASE_URL/POSTGRES_URL/PGDATABASE_URL) when present.
    2) Normalize common preview misconfigurations by applying POSTGRES_HOST/POSTGRES_PORT
       (and PGHOST/PGPORT) overrides when set.
    3) If the URL host is localhost-like and no explicit host override is supplied,
       fall back to the service hostname "auth_database" (the DB container name).
    4) If connecting to "auth_database" and no explicit port override is supplied,
       default to 5000 (matches auth_database/startup.sh in this repo).

    Returns:
        str: SQLAlchemy database URL.

    Raises:
        RuntimeError: If no usable set of DB env vars are present.
    """
    # Internal Postgres port used by the auth_database container in this repo.
    # NOTE: This is intentionally an app default (not an env var) because preview
    # environments often inject only partial DB env vars into dependent containers.
    DEFAULT_INTERNAL_POSTGRES_PORT = 5000

    # 1) Prefer single URL env vars if present.
    url = _env_first("DATABASE_URL", "POSTGRES_URL", "PGDATABASE_URL")
    if url:
        # Apply optional host/port overrides. This is especially important in preview where
        # POSTGRES_URL may contain "localhost" (DB container POV) or an external proxy port.
        override_host = _env_first("POSTGRES_HOST", "PGHOST")
        override_port = _env_first("POSTGRES_PORT", "PGPORT")

        # If URL targets localhost and no explicit host override is supplied,
        # assume the database is reachable via the DB container service name.
        localhost_like = (
            "://localhost" in url or "://127.0.0.1" in url or "://0.0.0.0" in url
        )
        if not override_host and localhost_like:
            override_host = "auth_database"

        # Local import to keep module import time minimal.
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)

        # If we are targeting the DB service hostname but have no explicit port override,
        # force the internal port default (5000). This handles cases where the URL
        # has an external/proxy port that is not routable inside the container network.
        if (override_host or parsed.hostname) == "auth_database" and not override_port:
            override_port = str(DEFAULT_INTERNAL_POSTGRES_PORT)

        if override_host or override_port:
            username = parsed.username
            password = parsed.password
            hostname = override_host or (parsed.hostname or "")
            port = int(override_port) if override_port else parsed.port

            # Rebuild netloc, preserving credentials when present.
            auth = ""
            if username:
                auth = username
                if password is not None:
                    auth += f":{password}"
                auth += "@"

            netloc = f"{auth}{hostname}"
            if port:
                netloc += f":{port}"

            parsed = parsed._replace(netloc=netloc)
            url = urlunparse(parsed)

        # If user supplies a plain `postgresql://...` URL, SQLAlchemy can still use it
        # with psycopg2 installed. Keep the scheme as provided.
        return url

    # 2) Compose from components; support both POSTGRES_* and PG* conventions.
    host = _env_first("POSTGRES_HOST", "PGHOST") or "auth_database"
    port = _env_first("POSTGRES_PORT", "PGPORT")
    user = _env_first("POSTGRES_USER", "PGUSER")
    password = _env_first("POSTGRES_PASSWORD", "PGPASSWORD")
    db = _env_first("POSTGRES_DB", "PGDATABASE")

    missing = [
        k
        for k, v in {
            "POSTGRES_PORT/PGPORT": port,
            "POSTGRES_USER/PGUSER": user,
            "POSTGRES_PASSWORD/PGPASSWORD": password,
            "POSTGRES_DB/PGDATABASE": db,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(
            "Missing required database environment variables: "
            + ", ".join(missing)
            + ". Please configure them in the backend container .env via the orchestrator."
        )

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


@lru_cache(maxsize=1)
def _get_engine() -> Engine:
    """Create (and memoize) the SQLAlchemy Engine.

    IMPORTANT: This is intentionally lazy so importing the FastAPI app does not
    fail when DB env vars are not available yet. This helps the server start and
    bind its port so readiness checks can hit the health endpoint.
    """
    database_url = _build_database_url()
    # Note: `pool_pre_ping=True` makes the engine more robust to dropped connections.
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _get_sessionmaker() -> sessionmaker:
    """Create (and memoize) the SQLAlchemy sessionmaker."""
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session and ensures it closes.

    If database environment variables are missing or the database is unreachable,
    this raises an HTTP 503 so route handlers do not crash with opaque 500 errors.

    Yields:
        sqlalchemy.orm.Session: Database session.

    Raises:
        fastapi.HTTPException: 503 when DB cannot be initialized.
    """
    try:
        SessionLocal = _get_sessionmaker()
        db = SessionLocal()
    except Exception as exc:
        # Typically: missing env vars (RuntimeError from _build_database_url)
        # or connection/driver issues during engine creation.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured or not reachable. Please ensure POSTGRES_* (or DATABASE_URL) env vars are set.",
        ) from exc

    try:
        yield db
    finally:
        db.close()
