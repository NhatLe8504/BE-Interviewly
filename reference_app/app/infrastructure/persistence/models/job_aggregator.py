from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base


class JobSourceRecord(Base):
    __tablename__ = "job_sources"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    crawl_interval_m: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    postings: Mapped[list[JobPostingRecord]] = relationship(
        "JobPostingRecord", back_populates="source", cascade="all, delete-orphan",
    )


class JobCompanyRecord(Base):
    __tablename__ = "job_companies"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    postings: Mapped[list[JobPostingRecord]] = relationship(
        "JobPostingRecord", back_populates="company", cascade="all, delete-orphan",
    )


class JobPostingRecord(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        Index("idx_job_postings_status", "status"),
        Index("idx_job_postings_fingerprint", "content_fingerprint"),
        Index("idx_job_postings_seniority", "seniority"),
        Index("idx_job_postings_domain_id", "domain_id"),
        Index("idx_job_postings_created_at", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("job_sources.source_id", ondelete="CASCADE"), nullable=False,
    )
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_companies.company_id", ondelete="CASCADE"), nullable=False,
    )
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_domains.domain_id", ondelete="SET NULL"), nullable=True,
    )
    seniority: Mapped[str] = mapped_column(String(32), nullable=False, default="mid")
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full_time")
    workplace_type: Mapped[str] = mapped_column(String(32), nullable=False, default="hybrid")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="VND")
    is_salary_negotiable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    skills_required: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    technologies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    original_apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    via_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    source: Mapped[JobSourceRecord] = relationship("JobSourceRecord", back_populates="postings")
    company: Mapped[JobCompanyRecord] = relationship("JobCompanyRecord", back_populates="postings")
