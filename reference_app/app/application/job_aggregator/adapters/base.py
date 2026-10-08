from __future__ import annotations

from abc import ABC, abstractmethod
import html
import re
from typing import Any

from ....domain.job_aggregator import (
    JobEmploymentType,
    JobSeniority,
    JobWorkplaceType,
)

COMMON_TECH_KEYWORDS = [
    "Java", "Spring Boot", "Spring", "Python", "FastAPI", "Django", "Flask",
    "TypeScript", "JavaScript", "React", "Next.js", "Vue", "Angular", "Node.js", "Express", "NestJS",
    "Golang", "Go", "C#", ".NET", ".NET Core", "C++", "Rust", "PHP", "Laravel",
    "Kotlin", "Swift", "Flutter", "React Native",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQL", "NoSQL",
    "Kafka", "RabbitMQ", "GraphQL", "REST API", "Microservices", "System Design",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "CI/CD", "Git", "Linux",
    "Machine Learning", "AI", "NLP", "LLM", "Deep Learning", "PyTorch", "TensorFlow",
]


class BaseJobSourceAdapter(ABC):
    @abstractmethod
    async def fetch_jobs(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Fetches raw jobs and returns a normalized dictionary list."""
        pass

    @staticmethod
    def normalize_text(raw_html_or_text: str) -> str:
        if not raw_html_or_text:
            return ""
        clean = re.sub(r"<[^>]+>", " ", raw_html_or_text)
        clean = html.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def detect_seniority(title: str, text: str = "") -> JobSeniority:
        combined = f"{title} {text}".lower()
        if any(w in combined for w in ["intern", "thực tập", "trainee"]):
            return JobSeniority.intern
        if any(w in combined for w in ["fresher", "mới tốt nghiệp"]):
            return JobSeniority.fresher
        if any(w in combined for w in ["junior", "1 năm", "1-2 năm", "1 - 2 năm"]):
            return JobSeniority.junior
        if any(w in combined for w in ["principal", "staff", "head", "lead", "trưởng nhóm"]):
            return JobSeniority.lead
        if any(w in combined for w in ["senior", "chuyên viên cao cấp", "sr.", "sr "]):
            return JobSeniority.senior
        return JobSeniority.mid

    @staticmethod
    def detect_workplace_type(title: str, location: str = "", text: str = "") -> JobWorkplaceType:
        combined = f"{title} {location} {text}".lower()
        if "remote" in combined or "từ xa" in combined or "work from home" in combined:
            return JobWorkplaceType.remote
        if "hybrid" in combined or "linh hoạt" in combined:
            return JobWorkplaceType.hybrid
        return JobWorkplaceType.on_site

    @staticmethod
    def detect_employment_type(title: str, text: str = "") -> JobEmploymentType:
        combined = f"{title} {text}".lower()
        if "part time" in combined or "part-time" in combined or "bán thời gian":
            return JobEmploymentType.part_time
        if "contract" in combined or "hợp đồng" in combined or "freelance" in combined:
            return JobEmploymentType.contract
        if "intern" in combined or "thực tập" in combined:
            return JobEmploymentType.internship
        return JobEmploymentType.full_time

    @classmethod
    def extract_tech_keywords(cls, title: str, text: str = "") -> tuple[list[str], list[str]]:
        combined = f" {title} {text} "
        found_skills: list[str] = []
        for kw in COMMON_TECH_KEYWORDS:
            pattern = r"(?i)(?:\b|_)" + re.escape(kw) + r"(?:\b|_)"
            if re.search(pattern, combined):
                found_skills.append(kw)
        skills_required = found_skills[:8]
        technologies = found_skills[:12]
        return skills_required, technologies
