from datetime import datetime, timezone
import json

from bs4 import BeautifulSoup
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.application.job_aggregator.adapters.base import BaseJobSourceAdapter
from app.application.job_aggregator.adapters.company_branding import collect_company_branding, page_job_metadata
from app.domain.job_metadata import detect_countries, detect_seniority, is_global_remote, parse_source_datetime
from app.infrastructure.orm import Base
from app.infrastructure.persistence.job_aggregator_repository import SqlAlchemyJobAggregatorRepository
from app.infrastructure.persistence.job_metadata_migration import migrate_job_metadata
from app.infrastructure.persistence.models.job_aggregator import JobCompanyRecord, JobPostingRecord, JobSourceRecord


@pytest.mark.parametrize("title,description,expected", [
    ("DevOps Engineer", "Internal tools for international teams using the internet", "unknown"),
    ("Senior Java Developer", "Mentor interns", "senior"),
    ("Software Engineering Intern", "", "intern"),
    ("Deployment Strategist", "Work with senior team members", "unknown"),
    ("Backend Developer", "Cấp bậc: Junior", "junior"),
    ("Junior Python Developer", "", "junior"),
    ("Cloud Infrastructure Lead", "", "lead"),
])
def test_seniority_requires_role_evidence(title, description, expected):
    assert detect_seniority(title, description).value == expected


def test_employment_and_technology_are_not_guessed():
    assert BaseJobSourceAdapter.detect_employment_type("Engineer").value == "unknown"
    assert BaseJobSourceAdapter.detect_employment_type("Engineer", "Full-time").value == "full_time"
    assert BaseJobSourceAdapter.detect_employment_type("Engineer", "Bán thời gian").value == "part_time"
    skills, technologies = BaseJobSourceAdapter.extract_tech_keywords("DevOps Engineer", "Go to our careers page. Docker, Kubernetes, Python.")
    assert "Go" not in technologies
    assert "Docker" in skills
    assert "Java" not in BaseJobSourceAdapter.extract_tech_keywords("JavaScript Developer")[0]
    assert BaseJobSourceAdapter.extract_tech_keywords("Golang Developer")[0] == ["Go"]


def test_remote_does_not_mean_available_in_vietnam():
    assert detect_countries("Hồ Chí Minh City, Vietnam") == ["VN"]
    assert detect_countries("Madrid, Spain") == ["ES"]
    assert detect_countries("Remote, United States") == ["US"]
    assert is_global_remote("Home based - Worldwide", "remote")
    assert not is_global_remote("Home based - Americas", "remote")
    assert not is_global_remote("Remote, Germany", "remote")


def company_document(company_name="Example Company"):
    payload = {
        "@type": "JobPosting", "hiringOrganization": {"name": company_name, "logo": "/logo.png"},
        "datePosted": "2026-09-15T12:00:00Z", "employmentType": "FULL_TIME",
        "jobLocation": {"address": {"addressLocality": "Hà Nội", "addressCountry": "Vietnam"}},
    }
    return BeautifulSoup('<script type="application/ld+json">' + json.dumps(payload) + '</script><img class="company-cover" src="/office.jpg">', "html.parser")


def approved_policy():
    return {"company_branding": {
        "reuse_allowed": True, "license_url": "https://employer.example/brand-policy",
        "allowed_image_hosts": ["employer.example"], "banner_selectors": [".company-cover"],
    }}


def test_branding_requires_permission_identity_and_valid_domain():
    source_url = "https://employer.example/jobs/123"
    assert collect_company_branding(company_document(), source_url, "Example Company", {}) == {}
    assert collect_company_branding(company_document("Other Company"), source_url, "Example Company", approved_policy()) == {}
    branding = collect_company_branding(company_document(), source_url, "Example Company", approved_policy())
    assert branding["company_banner_url"] == "https://employer.example/office.jpg"
    assert branding["company_logo_url"] == "https://employer.example/logo.png"
    assert branding["branding_source_url"] == source_url
    forbidden_policy = approved_policy()
    forbidden_policy["company_branding"]["allowed_image_hosts"] = ["different.example"]
    assert collect_company_branding(company_document(), source_url, "Example Company", forbidden_policy) == {}


def test_source_dates_and_location_survive_parsing():
    metadata = page_job_metadata(company_document(), "https://employer.example/jobs/123", "Example Company", {})
    assert metadata["posted_at"] == datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    assert metadata["location"] == "Hà Nội, Vietnam"
    assert metadata["employment_type"] == "full_time"
    assert "company_banner_url" not in metadata
    assert parse_source_datetime("not a timestamp") is None
    assert parse_source_datetime(0) is None


@pytest.fixture
def isolated_database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[JobCompanyRecord.__table__, JobSourceRecord.__table__, JobPostingRecord.__table__])
    yield engine
    engine.dispose()


def posting_data(external_id, location):
    return {
        "source_id": "greenhouse", "external_job_id": external_id, "company_name": "Example Company",
        "title": "DevOps Engineer", "location": location,
        "workplace_type": "remote" if "Home based" in location else "unknown",
        "original_apply_url": f"https://employer.example/jobs/{external_id}",
        "content_fingerprint": external_id, "cleaned_jd_text": "Develop internal platforms.",
    }


def test_repository_keeps_unknowns_and_real_posting_date(isolated_database):
    with Session(isolated_database) as session:
        repository = SqlAlchemyJobAggregatorRepository(session)
        vietnam_job, _ = repository.upsert_job(posting_data("vn", "Hà Nội, Vietnam"))
        repository.upsert_job(posting_data("us", "New York, United States"))
        repository.upsert_job(posting_data("world", "Home based - Worldwide"))
        repository.upsert_job(posting_data("americas", "Home based - Americas"))
        session.commit()
        assert vietnam_job.seniority == "unknown"
        assert vietnam_job.posted_at is None
        assert vietnam_job.company.logo_url is None
        items, total = repository.list_jobs()
        assert total == 2
        assert {item.external_job_id for item in items} == {"vn", "world"}
        assert repository.list_jobs(country_code="")[1] == 4
        assert repository.list_jobs(country_code="US")[1] == 1
        created_at = vietnam_job.first_seen_at
        data = posting_data("vn", "Hà Nội, Vietnam")
        data["posted_at"] = "2026-09-15T12:00:00Z"
        refreshed, is_new = repository.upsert_job(data)
        assert not is_new
        assert refreshed.first_seen_at == created_at
        assert refreshed.posted_at == datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def test_migration_repairs_legacy_guesses_once(isolated_database):
    with Session(isolated_database) as session:
        repository = SqlAlchemyJobAggregatorRepository(session)
        posting, _ = repository.upsert_job(posting_data("legacy", "Hà Nội, Vietnam"))
        posting.seniority = "intern"
        posting.employment_type = "part_time"
        posting.posted_at = posting.first_seen_at
        posting.technologies = ["Go", "Docker"]
        posting.metadata_revision = 0
        session.commit()
    migrate_job_metadata(isolated_database)
    migrate_job_metadata(isolated_database)
    with Session(isolated_database) as session:
        posting = session.scalar(select(JobPostingRecord))
        assert posting.seniority == "unknown"
        assert posting.employment_type == "unknown"
        assert posting.posted_at is None
        assert posting.technologies == ["Docker"]
        assert posting.country_codes == ["VN"]
        assert posting.metadata_revision == 2
