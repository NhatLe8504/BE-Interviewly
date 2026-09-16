from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    otp: str | None = Field(default=None, max_length=10)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str
    status: str


class SendOtpIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    purpose: str = Field(default="verify_email", max_length=50)


class VerifyOtpIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    otp: str = Field(min_length=1, max_length=10)
    purpose: str = Field(default="verify_email", max_length=50)


class GoogleAuthIn(BaseModel):
    credential: str = Field(min_length=10)


class MessageOut(BaseModel):
    message: str
