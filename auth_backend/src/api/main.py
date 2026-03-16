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

from src.db import engine
from src.models import User  # noqa: F401 (import ensures model metadata is registered)
from src.db import Base
from src.api.auth_routes import router as auth_router

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
# In production, restrict allow_origins to the deployed frontend URL(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_create_tables() -> None:
    """Create database tables at startup (simple bootstrap for this template)."""
    # For production, use proper migrations (Alembic). For this project template,
    # creating tables on startup keeps setup friction low.
    Base.metadata.create_all(bind=engine)


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
