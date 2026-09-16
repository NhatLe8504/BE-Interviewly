from __future__ import annotations

import json

from fastapi.encoders import jsonable_encoder

from app.config import API_TITLE, API_VERSION
from app.main import export_openapi


def test_openapi_file_syncs_with_app(client) -> None:
    out = export_openapi(client.app)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    live = jsonable_encoder(client.app.openapi())
    assert on_disk == live


def test_openapi_single_source_version_and_title(client) -> None:
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == API_TITLE
    assert spec["info"]["version"] == API_VERSION
