from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.bootstrap import build_services
from app.infrastructure.memory.state import MemoryState
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def state() -> MemoryState:
    fresh = MemoryState()
    fresh.seed()
    return fresh


@pytest.fixture
def client(state: MemoryState) -> TestClient:
    return TestClient(create_app(build_services(state)))
