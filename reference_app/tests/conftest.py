from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

@pytest.fixture
def client():
    from app.bootstrap import build_services
    from app.main import create_app
    from fastapi.testclient import TestClient

    return TestClient(create_app(build_services()))

