from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://interviewly:interviewly@localhost:5432/interviewly"
)


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        )
