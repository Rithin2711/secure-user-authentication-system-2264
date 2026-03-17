"""
Database connectivity check utility for the auth_backend.

This script is intended for preview debugging/verification and CI smoke checks.
It uses the same DB configuration code as the FastAPI app (src.db) and attempts a
simple `SELECT 1`.

Usage:
    python -m src.check_db_connection

Exit codes:
    0: Successfully connected and executed a test query.
    2: Failed to initialize engine or connect/query.
"""

from __future__ import annotations

from sqlalchemy import text

from src.db import _get_engine


# PUBLIC_INTERFACE
def main() -> None:
    """Run a simple DB connectivity check.

    Raises:
        SystemExit: with code 2 if connection/query fails.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB connection OK")
    except Exception as exc:
        # Keep output short and actionable for preview logs.
        print(f"DB connection FAILED: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
