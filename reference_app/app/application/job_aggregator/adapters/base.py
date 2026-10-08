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
from ....domain.job_metadata import detect_employment_type, detect_seniority, detect_workplace_type

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
        return detect_seniority(title, text)

    @staticmethod
    def detect_workplace_type(title: str, location: str = "", text: str = "") -> JobWorkplaceType:
        return detect_workplace_type(title, location, text)

    @staticmethod
    def detect_employment_type(title: str, text: str = "") -> JobEmploymentType:
        return detect_employment_type(title, text)

    @classmethod
    def extract_tech_keywords(cls, title: str, text: str = "") -> tuple[list[str], list[str]]:
        combined = f" {title} {text} "
        found_skills: list[str] = []
        for kw in COMMON_TECH_KEYWORDS:
            if kw == "Go":
                go_context = r"\b(?:golang|go (?:programming|language|developer|engineer)|(?:programming|language|backend) (?:in |with )?go)\b"
                if not re.search(go_context, combined, re.I) and not re.search(r"\bGo\b", title):
                    continue
            pattern = r"(?i)(?:\b|_)" + re.escape(kw) + r"(?:\b|_)"
            if re.search(pattern, combined):
                canonical_keyword = "Go" if kw == "Golang" else kw
                if canonical_keyword not in found_skills:
                    found_skills.append(canonical_keyword)
        skills_required = found_skills[:8]
        technologies = found_skills[:12]
        return skills_required, technologies
