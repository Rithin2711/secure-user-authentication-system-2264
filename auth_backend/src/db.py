"""
Database configuration and session management.

Uses SQLAlchemy with a synchronous PostgreSQL driver. The database connection
details are provided via environment variables.

Required env vars (must be set via orchestrator/.env for the backend container):
- POSTGRES_URL or POSTGRES_HOST (optional, see below)
- POSTGRES_PORT
- POSTGRES_USER
- POSTGRES_PASSWORD
- POSTGRES_DB

Connection resolution:
- If POSTGRES_URL is set, it is used directly.
- Otherwise a URL is composed from POSTGRES_HOST (default: localhost) and the
  other required variables.
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _build_database_url() -> str:
    """Build a PostgreSQL connection URL from environment variables."""
    postgres_url = os.getenv("POSTGRES_URL")
    if postgres_url:
        return postgres_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")

    missing = [k for k, v in {
        "POSTGRES_PORT": port,
        "POSTGRES_USER": user,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": db,
    }.items() if not v]
    if missing:
        raise RuntimeError(
            "Missing required database environment variables: "
            + ", ".join(missing)
            + ". Please configure them in the backend container .env via the orchestrator."
        )

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = _build_database_url()

# Note: `pool_pre_ping=True` makes the engine more robust to dropped connections.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


# PUBLIC_INTERFACE
def get_db() -> Generator:
    """FastAPI dependency that yields a SQLAlchemy session and ensures it closes.

    Yields:
        sqlalchemy.orm.Session: Database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
