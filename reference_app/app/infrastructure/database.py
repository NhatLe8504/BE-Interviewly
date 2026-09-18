from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def create_engine_from_url(database_url: str) -> Engine:
    connect_args: dict = {}
    if not database_url.startswith("sqlite"):
        connect_args["connect_timeout"] = 2
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def check_database(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return "down"
    return "up"
