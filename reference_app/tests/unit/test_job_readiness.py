from datetime import datetime, timezone
from app.application.skills.estimator import SkillEstimateResult
from app.application.skills.readiness import JobReadinessEvaluator


def test_job_readiness_insufficient_data():
    assessment = JobReadinessEvaluator.evaluate(
        job_id="test_job_1",
        job_title="Backend Developer (Java)",
        job_seniority="mid",
        skills_required=["Java", "Spring Boot", "Kafka"],
        technologies=["PostgreSQL", "Docker"],
        cleaned_jd_text="Looking for mid-level Java backend engineer with Spring Boot, Kafka, Docker.",
        user_skills={},  # Empty user skills
    )
    assert assessment.verdict == "insufficient_data"
    assert assessment.data_coverage == 0.0
    assert assessment.match_percent == 0
    assert len(assessment.requirements) >= 3


def test_job_readiness_ready():
    now = datetime.now(timezone.utc)
    user_skills = {
        "java": SkillEstimateResult("java", 3.2, "middle", 0.85, 5, 3, now),
        "spring-boot": SkillEstimateResult("spring-boot", 3.0, "middle", 0.80, 4, 3, now),
        "postgresql": SkillEstimateResult("postgresql", 3.1, "middle", 0.80, 4, 3, now),
        "docker": SkillEstimateResult("docker", 2.8, "middle", 0.70, 3, 2, now),
    }

    assessment = JobReadinessEvaluator.evaluate(
        job_id="test_job_2",
        job_title="Java Software Engineer",
        job_seniority="mid",
        skills_required=["Java", "Spring Boot"],
        technologies=["PostgreSQL", "Docker"],
        cleaned_jd_text="Java, Spring Boot, PostgreSQL, Docker",
        user_skills=user_skills,
    )
    assert assessment.verdict == "ready"
    assert assessment.match_percent >= 80
    assert assessment.data_coverage >= 0.8


def test_job_readiness_gap_cannot_be_ready():
    now = datetime.now(timezone.utc)
    # User is beginner in Java, but Senior is required
    user_skills = {
        "java": SkillEstimateResult("java", 1.2, "junior", 0.85, 5, 1, now),
        "spring-boot": SkillEstimateResult("spring-boot", 1.0, "beginner", 0.80, 4, 1, now),
    }

    assessment = JobReadinessEvaluator.evaluate(
        job_id="test_job_3",
        job_title="Senior Java Developer",
        job_seniority="senior",
        skills_required=["Java", "Spring Boot"],
        technologies=[],
        cleaned_jd_text="Senior Java Developer with Spring Boot",
        user_skills=user_skills,
    )
    # Must gap exists (junior/beginner vs senior), verdict must not be ready
    assert assessment.verdict != "ready"
    assert "spring-boot" in assessment.recommended_skills or "java" in assessment.recommended_skills

def test_unknown_requirements_stay_in_match_denominator():
    """LOI #6: chỉ 2/5 yêu cầu có bằng chứng thì không được báo 100% hay ready."""
    now = datetime.now(timezone.utc)
    user_skills = {
        "java": SkillEstimateResult("java", 3.2, "middle", 0.85, 5, 3, now),
        "sql": SkillEstimateResult("sql", 3.2, "middle", 0.85, 5, 3, now),
    }

    assessment = JobReadinessEvaluator.evaluate(
        job_id="test_job_loi6",
        job_title="Backend Engineer",
        job_seniority="mid",
        skills_required=["Java", "SQL", "Kafka", "Docker", "Redis"],
        technologies=[],
        cleaned_jd_text="",
        user_skills=user_skills,
    )

    assert assessment.match_percent == 40
    assert assessment.data_coverage == 0.4
    assert assessment.verdict == "insufficient_data"
    unknown = {it.skill_id for it in assessment.requirements if it.status == "unknown"}
    assert {"kafka", "docker", "redis"} <= unknown


def test_ready_requires_verified_must_haves_and_real_coverage():
    """Ready đòi hỏi mọi kỹ năng bắt buộc đã được kiểm chứng và độ phủ dữ liệu >= 50%."""
    now = datetime.now(timezone.utc)
    # Trường hợp 1: toàn bộ must-have đạt nhưng chỉ 1/4 kỹ năng có bằng chứng -> không ready.
    thin = {
        "java": SkillEstimateResult("java", 3.2, "middle", 0.85, 5, 3, now),
    }
    assessment = JobReadinessEvaluator.evaluate(
        job_id="test_job_thin",
        job_title="Backend Engineer",
        job_seniority="mid",
        skills_required=["Java"],
        technologies=["Kafka", "Docker", "Redis"],
        cleaned_jd_text="",
        user_skills=thin,
    )
    assert assessment.match_percent == 75
    assert assessment.verdict == "almost"

    # Trường hợp 2: must-have đầy đủ bằng chứng, độ phủ 50% -> ready.
    enough = {
        "java": SkillEstimateResult("java", 3.2, "middle", 0.85, 5, 3, now),
        "sql": SkillEstimateResult("sql", 3.2, "middle", 0.85, 5, 3, now),
    }
    assessment2 = JobReadinessEvaluator.evaluate(
        job_id="test_job_enough",
        job_title="Backend Engineer",
        job_seniority="mid",
        skills_required=["Java", "SQL"],
        technologies=["Kafka", "Docker"],
        cleaned_jd_text="",
        user_skills=enough,
    )
    assert assessment2.verdict == "ready"
    assert assessment2.match_percent == 75
    assert assessment2.data_coverage == 0.5
