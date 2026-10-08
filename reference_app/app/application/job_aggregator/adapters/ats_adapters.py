from __future__ import annotations

import logging
from typing import Any
import uuid

import httpx

from ....domain.job_aggregator import compute_job_fingerprint
from .base import BaseJobSourceAdapter

logger = logging.getLogger(__name__)


class GreenhouseAdapter(BaseJobSourceAdapter):
    def __init__(self, board_tokens: list[str] | None = None, timeout: float = 12.0) -> None:
        self.board_tokens = board_tokens or ["gitlab", "cloudflare"]
        self.timeout = timeout

    async def fetch_jobs(self, query: str = "", limit: int = 15) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for token in self.board_tokens:
                url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    jobs = data.get("jobs", [])
                    for j in jobs:
                        title = j.get("title", "")
                        loc = j.get("location", {}).get("name", "Remote")
                        apply_url = j.get("absolute_url", "")
                        if not title or not apply_url:
                            continue
                        # Filter software/engineering roles
                        title_lower = title.lower()
                        if not any(k in title_lower for k in ["engineer", "developer", "backend", "frontend", "fullstack", "devops", "software", "architect", "data"]):
                            continue

                        skills, techs = self.extract_tech_keywords(title, loc)
                        seniority = self.detect_seniority(title)
                        workplace = self.detect_workplace_type(title, loc)
                        emp_type = self.detect_employment_type(title)
                        company_name = token.capitalize()
                        description = f"Vị trí: {title} tại {company_name}.\nĐịa điểm làm việc: {loc}.\nXem chi tiết và ứng tuyển tại bài đăng gốc."
                        fp = compute_job_fingerprint(company_name, title, description)

                        results.append({
                            "external_job_id": str(j.get("id")),
                            "source_id": "greenhouse",
                            "company_name": company_name,
                            "company_location": loc,
                            "title": title,
                            "location": loc,
                            "seniority": seniority.value,
                            "employment_type": emp_type.value,
                            "workplace_type": workplace.value,
                            "raw_description": description,
                            "cleaned_jd_text": description,
                            "skills_required": skills,
                            "technologies": techs,
                            "original_apply_url": apply_url,
                            "content_fingerprint": fp,
                            "via_source": "via Greenhouse",
                        })
                        if len(results) >= limit:
                            break
                except Exception as exc:
                    logger.warning("Failed fetching greenhouse jobs for %s: %s", token, exc)
                if len(results) >= limit:
                    break
        return results


class SeedFallbackAdapter(BaseJobSourceAdapter):
    """Provides realistic seeded jobs for Vietnamese tech market."""
    async def fetch_jobs(self, query: str = "", limit: int = 30) -> list[dict[str, Any]]:
        sample_jobs = [
            {
                "company_name": "MoMo (M_Service)",
                "title": "Senior Java Backend Engineer (Payment Gateway)",
                "location": "Hồ Chí Minh City",
                "seniority": "senior",
                "workplace_type": "hybrid",
                "employment_type": "full_time",
                "salary_min": 45000000,
                "salary_max": 65000000,
                "skills_required": ["Java", "Spring Boot", "Kafka", "PostgreSQL", "Microservices"],
                "technologies": ["Java", "Redis", "Docker", "Kubernetes", "AWS"],
                "via_source": "via ITviec",
                "original_apply_url": "https://momo.vn/tuyen-dung",
                "description": "Tham gia phát triển hệ thống lõi Payment Gateway phục vụ 30 triệu người dùng. Yêu cầu 4+ năm kinh nghiệm Java/Spring Boot, xử lý tải cao (High Concurrency), am hiểu Kafka, Redis caching và Clean Architecture.",
            },
            {
                "company_name": "VNG Corporation",
                "title": "Middle / Senior Golang Developer (ZaloPay Core)",
                "location": "Hồ Chí Minh City",
                "seniority": "mid",
                "workplace_type": "hybrid",
                "employment_type": "full_time",
                "salary_min": 35000000,
                "salary_max": 50000000,
                "skills_required": ["Golang", "Go", "gRPC", "MySQL", "Distributed Systems"],
                "technologies": ["Golang", "Docker", "Kafka", "Prometheus", "CI/CD"],
                "via_source": "via TopCV",
                "original_apply_url": "https://careers.vng.com.vn",
                "description": "Xây dựng các microservices hiệu năng cao cho hệ thống ZaloPay. Yêu cầu thành thạo Golang, gRPC, kiến trúc hướng sự kiện (Event-Driven Architecture) và cơ sở dữ liệu quan hệ MySQL/PostgreSQL.",
            },
            {
                "company_name": "FPT Software",
                "title": "Fullstack React & Node.js Developer (Global Client)",
                "location": "Hà Nội",
                "seniority": "mid",
                "workplace_type": "on_site",
                "employment_type": "full_time",
                "salary_min": 25000000,
                "salary_max": 40000000,
                "skills_required": ["React", "TypeScript", "Node.js", "Express", "REST API"],
                "technologies": ["TypeScript", "Next.js", "Tailwind CSS", "MongoDB", "Git"],
                "via_source": "via VietnamWorks",
                "original_apply_url": "https://fptsoftware.com/careers",
                "description": "Tham gia dự án chuyển đổi số cho đối tác tài chính Singapore và Nhật Bản. Yêu cầu 2+ năm kinh nghiệm lập trình React.js, TypeScript và Node.js. Tiếng Anh giao tiếp tốt trong công việc.",
            },
            {
                "company_name": "Viettel Solutions",
                "title": "DevOps / Cloud Platform Engineer (Kubernetes & AWS)",
                "location": "Hà Nội",
                "seniority": "senior",
                "workplace_type": "on_site",
                "employment_type": "full_time",
                "salary_min": 40000000,
                "salary_max": 60000000,
                "skills_required": ["Docker", "Kubernetes", "AWS", "CI/CD", "Linux"],
                "technologies": ["Terraform", "GitLab CI", "Prometheus", "Grafana", "Python"],
                "via_source": "via ITviec",
                "original_apply_url": "https://viettel.vn/tuyen-dung",
                "description": "Vận hành hạ tầng điện toán đám mây cho các giải pháp Chính phủ số và Doanh nghiệp lớn. Yêu cầu kinh nghiệm sâu về Kubernetes, container orchestration, tự động hóa CI/CD và kiến trúc bảo mật đám mây.",
            },
            {
                "company_name": "Techcombank",
                "title": "Junior / Middle Python & AI Engineer",
                "location": "Hà Nội",
                "seniority": "junior",
                "workplace_type": "hybrid",
                "employment_type": "full_time",
                "salary_min": 22000000,
                "salary_max": 35000000,
                "skills_required": ["Python", "FastAPI", "Machine Learning", "NLP", "SQL"],
                "technologies": ["Python", "PyTorch", "Docker", "PostgreSQL", "Git"],
                "via_source": "via LinkedIn",
                "original_apply_url": "https://techcombankjobs.com",
                "description": "Phát triển các mô hình AI/NLP xử lý tài liệu tự động và trợ lý ảo thông minh cho khối ngân hàng bán lẻ. Yêu cầu tư duy thuật toán tốt, thành thạo Python, FastAPI và thư viện xử lý dữ liệu.",
            },
            {
                "company_name": "One Mount Group",
                "title": "Senior Frontend Engineer (React / Next.js)",
                "location": "Hà Nội",
                "seniority": "senior",
                "workplace_type": "hybrid",
                "employment_type": "full_time",
                "salary_min": 40000000,
                "salary_max": 55000000,
                "skills_required": ["React", "Next.js", "TypeScript", "Performance Tuning", "UI/UX"],
                "technologies": ["React", "TypeScript", "GraphQL", "Tailwind CSS", "Jest"],
                "via_source": "via ITviec",
                "original_apply_url": "https://careers.onemount.com",
                "description": "Phụ trách kiến trúc giao diện người dùng cho hệ sinh thái VinShop & OneHousing. Yêu cầu chuyên môn sâu về Web Performance, SSR/SSG với Next.js và thiết kế UI Component System chuẩn mực.",
            },
        ]

        results: list[dict[str, Any]] = []
        for item in sample_jobs[:limit]:
            fp = compute_job_fingerprint(item["company_name"], item["title"], item["description"])
            results.append({
                "external_job_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, item["title"])),
                "source_id": "serper_jobs",
                "company_name": item["company_name"],
                "company_location": item["location"],
                "title": item["title"],
                "location": item["location"],
                "seniority": item["seniority"],
                "employment_type": item["employment_type"],
                "workplace_type": item["workplace_type"],
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "raw_description": item["description"],
                "cleaned_jd_text": item["description"],
                "skills_required": item["skills_required"],
                "technologies": item["technologies"],
                "original_apply_url": item["original_apply_url"],
                "content_fingerprint": fp,
                "via_source": item["via_source"],
            })
        return results
