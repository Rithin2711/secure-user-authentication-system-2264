"""
Authentication routes: signup and login.

Implements:
- POST /api/signup: create a user with hashed password (email unique)
- POST /api/login: validate password and return a JWT token
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import User
from src.schemas import AuthResponse, ErrorResponse, LoginRequest, SignupRequest
from src.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error or weak password."},
        409: {"model": ErrorResponse, "description": "Email already exists."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        503: {"model": ErrorResponse, "description": "Database is not configured or reachable."},
    },
    operation_id="signup",
    summary="Register a new user",
    description="Creates a new user account with a unique email and a bcrypt-hashed password.",
)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Register a new user and return a JWT token.

    Persists the submitted signup fields (name, phone, email, hashed password)
    into PostgreSQL.

    Returns:
        AuthResponse: JWT token + user identity fields and a success message.

    Raises:
        HTTPException:
            - 409 when the email is already registered
            - 503 when the DB is not configured/reachable
            - 500 on unexpected persistence errors
    """
    # Fast path: check whether the email already exists so we can return a clear 409
    # before attempting insert/commit.
    try:
        existing = db.query(User).filter(User.email == str(payload.email)).first()
    except HTTPException:
        # get_db() may raise 503 as HTTPException; re-raise as-is.
        raise
    except Exception as exc:
        # Defensive: if the session exists but query fails for any reason.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured or not reachable. Please ensure POSTGRES_* (or DATABASE_URL) env vars are set.",
        ) from exc

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Signup failed: email already registered.",
        )

    # Persist user with a hashed password.
    user = User(
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        email=str(payload.email),
        password_hash=hash_password(payload.password),
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Defensive: unique constraint can still be hit under race conditions.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Signup failed: email already registered.",
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed: could not create user.",
        ) from exc

    db.refresh(user)

    token = create_access_token(subject=str(user.id), extra_claims={"email": user.email})
    return AuthResponse(
        access_token=token,
        email=user.email,
        user_id=user.id,
        message="Signup successful",
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials."},
        400: {"model": ErrorResponse, "description": "Invalid request."},
        503: {"model": ErrorResponse, "description": "Database is not configured or reachable."},
    },
    operation_id="login",
    summary="Login",
    description="Validates credentials (email + password) against stored user records and returns a signed JWT access token.",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Login user and return a JWT token.

    Validates the provided password against the stored bcrypt hash in PostgreSQL.

    Returns:
        AuthResponse: JWT token + user identity fields and a success message.

    Raises:
        HTTPException:
            - 401 when credentials do not match
            - 503 when the DB is not configured/reachable
    """
    try:
        user = db.query(User).filter(User.email == str(payload.email)).first()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured or not reachable. Please ensure POSTGRES_* (or DATABASE_URL) env vars are set.",
        ) from exc

    if not user or not verify_password(payload.password, user.password_hash):
        # Required failure message for UI.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login failed: invalid email or password.",
        )

    token = create_access_token(subject=str(user.id), extra_claims={"email": user.email})
    return AuthResponse(
        access_token=token,
        email=user.email,
        user_id=user.id,
        message="Login successful",
    )
