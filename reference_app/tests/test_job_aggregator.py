from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.application.job_aggregator.adapters.recipe_engine import (
    DomainRecipeRegistry,
    is_relevant_it_job,
)


def test_domain_recipe_registry_loads_all():
    registry = DomainRecipeRegistry()
    recipes = registry.list_all()
    assert len(recipes) >= 7
    source_ids = [r.get("source_id") for r in recipes]
    assert "topcv" in source_ids
    assert "itviec" in source_ids
    assert "vietnamworks" in source_ids
    assert "greenhouse" in source_ids


def test_it_relevance_filter():
    # Valid IT roles
    assert is_relevant_it_job("Senior Java Backend Engineer") is True
    assert is_relevant_it_job("Frontend React Developer") is True
    assert is_relevant_it_job("DevOps / Cloud Platform Engineer") is True
    assert is_relevant_it_job("Data Scientist / AI Engineer") is True
    assert is_relevant_it_job("QA Automation Tester") is True

    # Invalid non-IT roles
    assert is_relevant_it_job("Senior Accountant") is False
    assert is_relevant_it_job("Accounts Payable Clerk") is False
    assert is_relevant_it_job("Sales Executive B2B") is False
    assert is_relevant_it_job("Office Administrator") is False
    assert is_relevant_it_job("HR Business Partner") is False


def test_jobs_api_endpoints():
    client = TestClient(app)

    # 1. List jobs
    resp = client.get("/api/v1/jobs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] > 0
    assert len(data["items"]) <= 5

    # Check first job schema
    first_job = data["items"][0]
    assert "job_id" in first_job
    assert "title" in first_job
    assert "original_apply_url" in first_job

    # 2. Get detail
    job_id = first_job["job_id"]
    det_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert det_resp.status_code == 200
    det_data = det_resp.json()
    assert det_data["job_id"] == job_id
    assert len(det_data["cleaned_jd_text"]) > 100

    # 3. Filter metadata
    meta_resp = client.get("/api/v1/jobs/metadata/filters")
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert "seniorities" in meta_data
    assert "top_technologies" in meta_data

    # 4. Sync status
    status_resp = client.get("/api/v1/jobs/sync/status")
    assert status_resp.status_code == 200
    assert "status" in status_resp.json()
