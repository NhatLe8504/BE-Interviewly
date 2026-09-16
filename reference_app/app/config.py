from __future__ import annotations

import os
from dataclasses import dataclass

API_TITLE = "BE-Interviewly"
API_VERSION = "0.1.0"
API_DESCRIPTION = "BE Interview Coach API."

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://interviewly:interviewly@localhost:5432/interviewly"
)
DEFAULT_JWT_SECRET = "dev-only-secret-change-me-please-set-JWT_SECRET-32-chars-min"
DEFAULT_JWT_EXPIRES_MINUTES = 1440
DEFAULT_GOOGLE_CLIENT_ID = ""
DEFAULT_GOOGLE_CLIENT_SECRET = ""
DEFAULT_SENDGRID_FROM_EMAIL = "fuji@mg.fuji.io.vn"
DEFAULT_SENDGRID_FROM_NAME = "FUJI"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expires_minutes: int = DEFAULT_JWT_EXPIRES_MINUTES
    google_client_id: str = DEFAULT_GOOGLE_CLIENT_ID
    google_client_secret: str = DEFAULT_GOOGLE_CLIENT_SECRET
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = DEFAULT_SENDGRID_FROM_EMAIL
    sendgrid_from_name: str = DEFAULT_SENDGRID_FROM_NAME

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            jwt_secret=os.environ.get("JWT_SECRET", DEFAULT_JWT_SECRET),
            jwt_expires_minutes=int(
                os.environ.get(
                    "JWT_EXPIRES_MINUTES", str(DEFAULT_JWT_EXPIRES_MINUTES),
                ),
            ),
            google_client_id=os.environ.get(
                "GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID,
            ),
            google_client_secret=os.environ.get(
                "GOOGLE_CLIENT_SECRET", DEFAULT_GOOGLE_CLIENT_SECRET,
            ),
            sendgrid_api_key=os.environ.get("SENDGRID_API_KEY", ""),
            sendgrid_from_email=os.environ.get(
                "SENDGRID_FROM_EMAIL", DEFAULT_SENDGRID_FROM_EMAIL,
            ),
            sendgrid_from_name=os.environ.get(
                "SENDGRID_FROM_NAME", DEFAULT_SENDGRID_FROM_NAME,
            ),
        )
