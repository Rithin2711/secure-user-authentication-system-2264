"""
Pydantic schemas for the authentication API.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic.alias_generators import to_camel
from pydantic import AliasChoices


_PASSWORD_MIN_LEN = 8
_PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$")


class SignupRequest(BaseModel):
    """Request body for user registration.

    Canonical request body (documented in OpenAPI):
        {
          "name": "Jane Doe",
          "phone": "+1 555 123 4567",
          "email": "user@example.com",
          "password": "Str0ngPassw0rd"
        }

    Compatibility notes (to prevent preview 422s due to client mismatch):
    - Accepts `fullName` as an alias for `name`.
    - Accepts `phoneNumber` as an alias for `phone`.
    - If `phone` is omitted, it is defaulted to "N/A" (still stored in DB).
      This preserves the DB's NOT NULL constraint while keeping API tolerant.
    """

    # Accept common alt key "fullName" used by some client forms.
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="User full name.",
        examples=["Jane Doe"],
        validation_alias=AliasChoices("name", "fullName"),
        serialization_alias="name",
    )

    # Tolerate missing phone by defaulting; accept common alt key "phoneNumber".
    phone: str = Field(
        "N/A",
        min_length=3,
        max_length=40,
        description="User phone number.",
        examples=["+1 555 123 4567"],
        validation_alias=AliasChoices("phone", "phoneNumber"),
        serialization_alias="phone",
    )

    email: EmailStr = Field(..., description="User email address (must be unique).", examples=["user@example.com"])
    password: str = Field(
        ...,
        min_length=_PASSWORD_MIN_LEN,
        description="Password (min 8 chars, must contain uppercase, lowercase, and number).",
        examples=["Str0ngPassw0rd"],
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # When clients omit phone we store a stable placeholder.
        v = (v or "").strip()
        return v if v else "N/A"

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < _PASSWORD_MIN_LEN:
            raise ValueError(f"Password must be at least {_PASSWORD_MIN_LEN} characters long.")
        if not _PASSWORD_REGEX.match(v):
            raise ValueError("Password must include at least one uppercase letter, one lowercase letter, and one number.")
        return v


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr = Field(..., description="Registered email address.", examples=["user@example.com"])
    password: str = Field(..., description="User password.", examples=["Str0ngPassw0rd"])


class AuthResponse(BaseModel):
    """Response returned after successful signup/login."""
    access_token: str = Field(..., description="JWT access token to authenticate subsequent requests.")
    token_type: str = Field("bearer", description="Token type (always 'bearer').")
    email: EmailStr = Field(..., description="User email.")
    user_id: int = Field(..., description="User id.")
    message: str = Field(..., description="Human-readable success message for the client UI.")


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Human-readable error message.")
    code: Optional[str] = Field(None, description="Optional stable error code for clients.")
