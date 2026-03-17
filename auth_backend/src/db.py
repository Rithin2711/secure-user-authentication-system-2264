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

    Returns:
        str: SQLAlchemy database URL.

    Raises:
        RuntimeError: If no usable set of DB env vars are present.
    """
    # 1) Prefer single URL env vars if present.
    url = _env_first("DATABASE_URL", "POSTGRES_URL", "PGDATABASE_URL")
    if url:
        # If user supplies a plain `postgresql://...` URL, SQLAlchemy can still
        # use it with psycopg2 installed. Keep as-is.
        return url

    # 2) Compose from components; support both POSTGRES_* and PG* conventions.
    host = _env_first("POSTGRES_HOST", "PGHOST") or "localhost"
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
