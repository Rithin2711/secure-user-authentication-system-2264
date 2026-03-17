"""
FastAPI application entrypoint for the authentication backend.

Provides:
- Health check: GET /
- Authentication API:
  - POST /api/signup
  - POST /api/login

Notes:
- Database connection is configured via POSTGRES_* environment variables.
- JWT signing is configured via JWT_SECRET (and optional JWT_ALGORITHM/JWT_EXPIRES_SECONDS).

Returns:
    FastAPI app instance exposed as `app`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.models import User  # noqa: F401 (import ensures model metadata is registered)
from src.db import Base
from src.api.auth_routes import router as auth_router

import os

openapi_tags = [
    {
        "name": "System",
        "description": "Health checks and operational endpoints.",
    },
    {
        "name": "Authentication",
        "description": "User signup and login endpoints.",
    },
]

app = FastAPI(
    title="Secure User Authentication System API",
    description="FastAPI backend providing user registration and login with PostgreSQL storage and JWT authentication.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# CORS: frontend will call this API from a browser.
#
# IMPORTANT:
# - If `allow_credentials=True`, you cannot reliably use `allow_origins=["*"]`
#   for browser-based requests. Browsers require an explicit origin echo.
# - Configure allowed origins via env var to match preview/prod frontend URLs.
#
# Env:
# - CORS_ALLOW_ORIGINS: comma-separated list of allowed origins
#   e.g. "https://my-frontend.example.com,https://localhost:3000"
#
# If not provided, we default to allowing the known preview frontend (port 3000)
# plus localhost dev defaults.
_allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _allow_origins_env:
    allow_origins = [o.strip() for o in _allow_origins_env.split(",") if o.strip()]
else:
    allow_origins = [
        "https://vscode-internal-33714-beta.beta01.cloud.kavia.ai:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_create_tables() -> None:
    """Create database tables at startup (simple bootstrap for this template).

    This is a best-effort bootstrap. If the database is not reachable or DB env
    vars are not provided in the preview environment, we should still allow the
    API server to start so it can bind its port and serve the health endpoint.
    """
    try:
        # Lazy import to avoid any DB configuration work at module import time.
        from src.db import _get_engine

        Base.metadata.create_all(bind=_get_engine())
    except Exception:
        # Do not crash the app on startup due to DB issues; route handlers will
        # still fail if DB is required, but container readiness should succeed.
        return


@app.get(
    "/",
    tags=["System"],
    summary="Health Check",
    description="Simple health check endpoint used for container readiness/liveness probes.",
    operation_id="health_check",
)
def health_check():
    """Health check endpoint.

    Returns:
        dict: `{ "message": "Healthy" }`
    """
    return {"message": "Healthy"}


app.include_router(auth_router)
