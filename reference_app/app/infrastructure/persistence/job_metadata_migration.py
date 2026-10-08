from __future__ import annotations

import re

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ...domain.job_metadata import (
    detect_countries, detect_employment_type, detect_seniority,
    detect_workplace_type, is_global_remote,
)
from .models.job_aggregator import JobPostingRecord


def migrate_job_metadata(engine) -> None:
    additions = {
        "job_companies": {
            "banner_url": "VARCHAR(1000)",
            "branding_source_url": "VARCHAR(1000)",
            "branding_license_url": "VARCHAR(1000)",
            "branding_reuse_allowed": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
        "job_postings": {
            "country_codes": "JSON NOT NULL DEFAULT '[]'",
            "is_global_remote": "BOOLEAN NOT NULL DEFAULT FALSE",
            "metadata_revision": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    inspector = inspect(engine)
    for table_name, columns in additions.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        with engine.begin() as connection:
            for column_name, definition in columns.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
    if not inspector.has_table("job_postings"):
        return
    with Session(engine) as session:
        postings = session.scalars(select(JobPostingRecord).where(JobPostingRecord.metadata_revision < 2))
        for posting in postings:
            if posting.source_id in {"topcv", "itviec", "vietnamworks", "linkedin"} and posting.location == "Việt Nam":
                posting.location = None
            posting.seniority = detect_seniority(posting.title, posting.cleaned_jd_text).value
            posting.employment_type = detect_employment_type(posting.title, posting.cleaned_jd_text).value
            posting.workplace_type = detect_workplace_type(posting.title, posting.location or "").value
            posting.country_codes = detect_countries(posting.location)
            posting.is_global_remote = is_global_remote(posting.location, posting.workplace_type)
            if posting.posted_at == posting.first_seen_at:
                posting.posted_at = None
            if not re.search(r"\b(?:golang|go (?:programming|language|developer|engineer))\b", posting.title + " " + posting.cleaned_jd_text, re.I):
                posting.technologies = [technology for technology in posting.technologies if technology != "Go"]
                posting.skills_required = [skill for skill in posting.skills_required if skill != "Go"]
            posting.metadata_revision = 2
        session.commit()
