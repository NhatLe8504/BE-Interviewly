from app.application.skills.taxonomy import get_default_taxonomy


def test_normalize_skill_aliases():
    taxonomy = get_default_taxonomy()
    assert taxonomy.normalize_skill_id("Golang") == "go"
    assert taxonomy.normalize_skill_id("go lang") == "go"
    assert taxonomy.normalize_skill_id("Spring Boot") == "spring-boot"
    assert taxonomy.normalize_skill_id("springboot") == "spring-boot"
    assert taxonomy.normalize_skill_id("k8s") == "kubernetes"
    assert taxonomy.normalize_skill_id("PostgreSQL") == "postgresql"
    assert taxonomy.normalize_skill_id("React.js") == "react"
    assert taxonomy.normalize_skill_id("unknown_xyz_random") is None


def test_extract_skills_from_text():
    taxonomy = get_default_taxonomy()
    text = "We are looking for a Senior Java Developer with Spring Boot, Redis, and Kafka experience."
    skills = taxonomy.extract_skills_from_text(text)
    skill_ids = {s.id for s in skills}
    assert "java" in skill_ids
    assert "spring-boot" in skill_ids
    assert "redis" in skill_ids
    assert "kafka" in skill_ids


def test_role_track_filtering():
    taxonomy = get_default_taxonomy()
    backend_skills = taxonomy.get_skills_for_role("backend")
    ids = {s.id for s in backend_skills}
    assert "java" in ids
    assert "spring-boot" in ids
    assert "postgresql" in ids

def test_bare_go_word_is_not_scanned_but_exact_tag_still_maps():
    taxonomy = get_default_taxonomy()
    scanned = {s.id for s in taxonomy.extract_skills_from_text("Go to our careers page. Docker, Kubernetes.")}
    assert "go" not in scanned
    assert "docker" in scanned
    # Tiêu đề có ngữ cảnh tuyển dụng vẫn nhận đúng Go.
    assert "go" in {s.id for s in taxonomy.extract_skills_from_text("We are hiring a Go Developer")}
    assert "go" in {s.id for s in taxonomy.extract_skills_from_text("Golang Developer")}
    # Tag chính xác do người dùng/ hệ thống gửi vào vẫn chuẩn hóa được.
    assert taxonomy.normalize_skill_id("Go") == "go"


def test_js_alias_does_not_match_inside_next_js():
    taxonomy = get_default_taxonomy()
    ids = {s.id for s in taxonomy.extract_skills_from_text("Ứng dụng Next.js có kích thước lớn")}
    assert "nextjs" in ids
    assert "javascript" not in ids
    assert taxonomy.normalize_skill_id("js") == "javascript"
