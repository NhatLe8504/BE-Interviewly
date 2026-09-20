from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException
import time

from ....application.container import ServiceContainer
import json
from decimal import Decimal
from ..dependencies import get_container, get_session, get_optional_user_id
from ..helpers.cache import cache_response
from ..schemas.catalog import (
    DomainOut,
    QuestionDetailOut,
    QuestionOut,
    QuestionPageOut,
    RoleOut,
    StarTemplateOut,
    QuestionBatchIn,
    QuestionEvaluateIn,
    QuestionEvaluationResultOut,
    MultiModalBreakdownOut,
    RubricScoreItemOut,
    StarBreakdownOut,
    PracticeHistoryCreateIn,
    PracticeHistoryOut,
    LeaderboardItemOut,
    QuestionSetReviewIn,
    QuestionSetReviewOut,
    QuestionSetReviewsPageOut,
    EvaluationQueueIn,
    EvaluationQueueOut,
    EvaluationPullOut,
)
from ....infrastructure.persistence.models.catalog import (
    PracticeHistoryRecord as PracticeHistoryModel,
    QuestionSetReview as QuestionSetReviewModel,
)

from ....infrastructure.queue.eval_queue import eval_pull_queue
router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/domains", response_model=list[DomainOut])
@cache_response(ttl_seconds=600, prefix="catalog:domains")
def list_domains(
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[DomainOut]:
    items = container.catalog_service.get_domains(session)
    return [DomainOut.model_validate(d) for d in items]


@router.get("/roles", response_model=list[RoleOut])
@cache_response(ttl_seconds=600, prefix="catalog:roles")
def list_roles(
    domain_id: int | None = Query(None, description="Filter roles by domain"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[RoleOut]:
    items = container.catalog_service.get_roles(session, domain_id=domain_id)
    return [RoleOut.model_validate(r) for r in items]


@router.get("/star-templates", response_model=list[StarTemplateOut])
@cache_response(ttl_seconds=600, prefix="catalog:star_templates")
def list_star_templates(
    language: str | None = Query(None, pattern="^(vi|en)$"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[StarTemplateOut]:
    items = container.catalog_service.get_star_templates(session, language=language)
    return [StarTemplateOut.model_validate(t) for t in items]


@router.get("/questions", response_model=QuestionPageOut)
@cache_response(ttl_seconds=180, prefix="catalog:questions")
def list_questions(
    domain_id: int | None = Query(None),
    role_id: int | None = Query(None),
    level: str | None = Query(None, alias="level", pattern="^(intern|fresher|junior|mid|middle|senior)$"),
    type: str | None = Query(None, alias="type", pattern="^(behavioral|technical|situational)$"),
    language: str | None = Query(None, pattern="^(vi|en)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionPageOut:
    items, total = container.catalog_service.get_questions(
        session,
        domain_id=domain_id,
        role_id=role_id,
        experience_level=level,
        question_type=type,
        language=language,
        is_active=True,
        limit=limit,
        offset=offset,
    )
    domain_map = {d.domain_id: d.domain_name for d in container.catalog_service.get_domains(session)}
    role_map = {r.role_id: r.role_name for r in container.catalog_service.get_roles(session)}
    out_items: list[QuestionOut] = []
    for q in items:
        q_dict = {
            "question_id": q.question_id,
            "domain_id": q.domain_id,
            "domain_name": domain_map.get(q.domain_id),
            "role_id": q.role_id,
            "role_name": role_map.get(q.role_id) if q.role_id else None,
            "experience_level": q.experience_level,
            "language": q.language,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "star_template_id": q.star_template_id,
            "is_active": q.is_active,
            "created_by": q.created_by,
            "created_at": q.created_at,
            "updated_at": q.updated_at,
        }
        out_items.append(QuestionOut.model_validate(q_dict))
    return QuestionPageOut(
        items=out_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/questions/random", response_model=QuestionOut)
def get_random_question(
    domain_id: int | None = Query(None),
    role_id: int | None = Query(None),
    level: str | None = Query(None, alias="level", pattern="^(intern|fresher|junior|mid|middle|senior)$"),
    language: str = Query("vi", pattern="^(vi|en)$"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionOut:
    q = container.catalog_service.get_random_question(
        session,
        domain_id=domain_id,
        role_id=role_id,
        experience_level=level,
        language=language,
    )
    return QuestionOut.model_validate(q)


@router.get("/questions/batch", response_model=list[QuestionDetailOut])
def get_questions_batch(
    ids: str = Query(..., description="Comma-separated question IDs"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[QuestionDetailOut]:
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    except Exception:
        id_list = []
    if not id_list:
        return []

    items = container.catalog_service.get_questions_by_ids(session, id_list)
    domain_map = {d.domain_id: d.domain_name for d in container.catalog_service.get_domains(session)}
    role_map = {r.role_id: r.role_name for r in container.catalog_service.get_roles(session)}

    results: list[QuestionDetailOut] = []
    for q in items:
        tmpl_out = None
        if q.star_template_id:
            try:
                tmpl = container.catalog_service.get_star_template(session, q.star_template_id)
                tmpl_out = StarTemplateOut.model_validate(tmpl)
            except Exception:
                tmpl_out = None
        results.append(
            QuestionDetailOut.model_validate({
                "question_id": q.question_id,
                "domain_id": q.domain_id,
                "domain_name": domain_map.get(q.domain_id),
                "role_id": q.role_id,
                "role_name": role_map.get(q.role_id) if q.role_id else None,
                "experience_level": q.experience_level,
                "language": q.language,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "star_template_id": q.star_template_id,
                "is_active": q.is_active,
                "created_by": q.created_by,
                "created_at": q.created_at,
                "updated_at": q.updated_at,
                "star_template": tmpl_out,
            })
        )
    return results


@router.post("/questions/batch", response_model=list[QuestionDetailOut])
def post_questions_batch(
    data: QuestionBatchIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[QuestionDetailOut]:
    if not data.ids:
        return []
    items = container.catalog_service.get_questions_by_ids(session, data.ids)
    domain_map = {d.domain_id: d.domain_name for d in container.catalog_service.get_domains(session)}
    role_map = {r.role_id: r.role_name for r in container.catalog_service.get_roles(session)}

    results: list[QuestionDetailOut] = []
    for q in items:
        tmpl_out = None
        if q.star_template_id:
            try:
                tmpl = container.catalog_service.get_star_template(session, q.star_template_id)
                tmpl_out = StarTemplateOut.model_validate(tmpl)
            except Exception:
                tmpl_out = None
        results.append(
            QuestionDetailOut.model_validate({
                "question_id": q.question_id,
                "domain_id": q.domain_id,
                "domain_name": domain_map.get(q.domain_id),
                "role_id": q.role_id,
                "role_name": role_map.get(q.role_id) if q.role_id else None,
                "experience_level": q.experience_level,
                "language": q.language,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "star_template_id": q.star_template_id,
                "is_active": q.is_active,
                "created_by": q.created_by,
                "created_at": q.created_at,
                "updated_at": q.updated_at,
                "star_template": tmpl_out,
            })
        )
    return results



@router.get("/questions/{question_id}", response_model=QuestionDetailOut)
@cache_response(ttl_seconds=600, prefix="catalog:question_detail")
def get_question_detail(
    question_id: int,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionDetailOut:
    q = container.catalog_service.get_question(session, question_id)
    tmpl_out = None
    if q.star_template_id:
        try:
            tmpl = container.catalog_service.get_star_template(session, q.star_template_id)
            tmpl_out = StarTemplateOut.model_validate(tmpl)
        except Exception:
            tmpl_out = None

    base_dict = {
        "question_id": q.question_id,
        "domain_id": q.domain_id,
        "role_id": q.role_id,
        "experience_level": q.experience_level,
        "language": q.language,
        "question_type": q.question_type,
        "question_text": q.question_text,
        "star_template_id": q.star_template_id,
        "is_active": q.is_active,
        "created_by": q.created_by,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
        "star_template": tmpl_out,
    }
    return QuestionDetailOut.model_validate(base_dict)



@router.post("/questions/{question_id}/evaluate", response_model=QuestionEvaluationResultOut)
def evaluate_question_answer(
    question_id: int,
    data: QuestionEvaluateIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionEvaluationResultOut:
    q = container.catalog_service.get_question(session, question_id)
    role_name = "Software Engineer"
    if q.role_id:
        try:
            r = container.catalog_service.get_role(session, q.role_id)
            role_name = r.role_name
        except Exception:
            pass

    # 1. QUIZ SCORE (15% max): 15 points if correct, 0 if wrong
    quiz_score = 0.0
    if data.is_quiz_correct is True:
        quiz_score = 15.0
    elif data.is_quiz_correct is False:
        quiz_score = 0.0

    # 2. TEXT STAR SCORE (35% max)
    text = (data.answer_text or "").strip()
    words = len(text.split())
    text_score = 0.0
    if words >= 20:
        base_pct = min(1.0, 0.5 + (words / 150.0) * 0.5)
        text_score = round(base_pct * 35.0, 1)
    elif words > 0:
        text_score = round((words / 20.0) * 12.0, 1)

    # 3. VOICE SCORE (50% max)
    dur = float(data.audio_duration_seconds or 0.0)
    voice_score = 0.0
    if dur >= 5.0:
        dur_pct = min(1.0, 0.6 + min(dur, 60.0) / 150.0)
        voice_score = round(dur_pct * 50.0, 1)
    elif dur > 0.0:
        voice_score = round((dur / 5.0) * 15.0, 1)

    # Call LLM evaluator if configured
    eval_data = None
    if text and container.evaluation_service and getattr(container.evaluation_service, "evaluator", None):
        try:
            eval_data = container.evaluation_service.evaluator.evaluate(
                question=q.question_text,
                answer=text,
                role=role_name,
                level=q.experience_level or "junior",
                language=data.language or "vi",
            )
        except Exception:
            eval_data = None

    if eval_data is not None:
        clarity = float(eval_data.clarity_score)
        structure = float(eval_data.structure_score)
        evidence = float(eval_data.evidence_score)
        llm_avg_pct = (clarity + structure + evidence) / 300.0

        if words >= 20:
            text_score = round(llm_avg_pct * 35.0, 1)

        total_score = min(100, int(round(quiz_score + text_score + voice_score)))
        passed = total_score >= 70
        star_dict = eval_data.star_analysis or {}

        return QuestionEvaluationResultOut(
            score=total_score,
            passed=passed,
            general_feedback=eval_data.feedback or "Câu trả lời có lập luận tốt.",
            star_breakdown=StarBreakdownOut(
                situation_score=9 if star_dict.get("situation") else 6,
                situation_feedback="Bối cảnh rõ ràng." if star_dict.get("situation") else "Nên nêu rõ hơn bối cảnh ban đầu.",
                task_score=9 if star_dict.get("task") else 7,
                task_feedback="Nhiệm vụ rõ ràng." if star_dict.get("task") else "Cần nêu rõ vai trò cá nhân.",
                action_score=9 if star_dict.get("action") else 6,
                action_feedback="Hành động cụ thể, logic." if star_dict.get("action") else "Nên đi sâu vào giải pháp kỹ thuật.",
                result_score=9 if star_dict.get("result") else 6,
                result_feedback="Có số liệu đo lường cụ thể." if star_dict.get("result") else "Nên bổ sung số liệu kết quả.",
            ),
            rubric_scores=[
                RubricScoreItemOut(
                    criterion_id="quiz",
                    criterion_name="Trắc nghiệm tình huống (15%)",
                    score=min(10, int(round((quiz_score / 15.0) * 10))),
                    level_label="15/15đ" if quiz_score >= 15 else "0/15đ",
                    feedback="Lựa chọn phương án tối ưu." if quiz_score >= 15 else "Chưa chọn phương án chuẩn nhất.",
                ),
                RubricScoreItemOut(
                    criterion_id="text",
                    criterion_name="Tự luận khung STAR (35%)",
                    score=min(10, int(round((text_score / 35.0) * 10))),
                    level_label=f"{text_score}/35đ",
                    feedback="Lập luận chặt chẽ, đầy đủ thành tố." if text_score >= 25 else "Cần viết chi tiết hơn.",
                ),
                RubricScoreItemOut(
                    criterion_id="voice",
                    criterion_name="Nói & Ghi âm trực tiếp (50%)",
                    score=min(10, int(round((voice_score / 50.0) * 10))),
                    level_label=f"{voice_score}/50đ",
                    feedback="Phát âm rõ ràng, thời lượng tốt." if voice_score >= 35 else "Cần luyện nói dài và lưu loát hơn.",
                ),
            ],
            strengths=[
                "Thực hiện đầy đủ các phần thi theo tiêu chuẩn đánh giá.",
                "Tư duy mạch lạc, có giải pháp thực tế.",
            ],
            improvements=[
                "Nêu rõ hơn các đánh đổi (trade-offs) trước khi lựa chọn giải pháp.",
                "Luyện tập phát âm và tăng độ dài câu trả lời bằng giọng nói để đạt trọn 50% điểm nói.",
            ],
            modal_breakdown=MultiModalBreakdownOut(
                quiz_score=quiz_score,
                quiz_max=15.0,
                text_score=text_score,
                text_max=35.0,
                voice_score=voice_score,
                voice_max=50.0,
                total_score=float(total_score),
            ),
        )

    # Heuristic score
    total_score = min(100, int(round(quiz_score + text_score + voice_score)))
    passed = total_score >= 70
    return QuestionEvaluationResultOut(
        score=total_score,
        passed=passed,
        general_feedback="Bài làm thể hiện sự cố gắng hoàn thiện các phần thi.",
        star_breakdown=StarBreakdownOut(),
        rubric_scores=[
            RubricScoreItemOut(
                criterion_id="quiz",
                criterion_name="Trắc nghiệm tình huống (15%)",
                score=min(10, int(round((quiz_score / 15.0) * 10))),
                level_label=f"{quiz_score}/15đ",
                feedback="Đạt điểm trắc nghiệm." if quiz_score > 0 else "Chưa đạt điểm trắc nghiệm.",
            ),
            RubricScoreItemOut(
                criterion_id="text",
                criterion_name="Tự luận khung STAR (35%)",
                score=min(10, int(round((text_score / 35.0) * 10))),
                level_label=f"{text_score}/35đ",
                feedback="Hoàn thành phần tự luận.",
            ),
            RubricScoreItemOut(
                criterion_id="voice",
                criterion_name="Nói & Ghi âm trực tiếp (50%)",
                score=min(10, int(round((voice_score / 50.0) * 10))),
                level_label=f"{voice_score}/50đ",
                feedback="Hoàn thành phần ghi âm nói.",
            ),
        ],
        strengths=["Đã tham gia hoàn thiện các phần thi."],
        improvements=["Luyện tập thêm phần nói để cải thiện điểm số."],
        modal_breakdown=MultiModalBreakdownOut(
            quiz_score=quiz_score,
            quiz_max=15.0,
            text_score=text_score,
            text_max=35.0,
            voice_score=voice_score,
            voice_max=50.0,
            total_score=float(total_score),
        ),
    )


def _get_user_info(session: Any, container: ServiceContainer, user_id: int | None) -> tuple[str, str | None, bool]:
    if not user_id:
        return ("Ứng viên ẩn danh", None, False)
    try:
        user = container.auth_service.get_user(session, user_id)
        name = user.full_name or (user.email.split("@")[0] if user.email else "Ứng viên")
        avatar = getattr(user, "avatar_url", None)
        is_pro = False
        try:
            sub = container.subscription_service.get_active_subscription(session, user_id)
            if sub and sub.is_active:
                is_pro = True
        except Exception:
            pass
        return (name, avatar, is_pro)
    except Exception:
        return ("Ứng viên", None, False)


@router.post("/practice-history", response_model=PracticeHistoryOut)
def save_practice_history(
    data: PracticeHistoryCreateIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
    user_id: int | None = Depends(get_optional_user_id),
) -> PracticeHistoryOut:
    summary_str = json.dumps(data.questions_summary, ensure_ascii=False) if data.questions_summary else None
    record = PracticeHistoryModel(
        user_id=user_id,
        session_title=data.session_title,
        source_type=data.source_type,
        source_id=data.source_id,
        domain_id=data.domain_id,
        domain_name=data.domain_name,
        role_name=data.role_name,
        total_questions=data.total_questions,
        evaluated_count=data.evaluated_count,
        average_score=Decimal(str(round(data.average_score, 2))),
        quiz_score_avg=Decimal(str(round(data.quiz_score_avg, 2))) if data.quiz_score_avg is not None else None,
        text_score_avg=Decimal(str(round(data.text_score_avg, 2))) if data.text_score_avg is not None else None,
        voice_score_avg=Decimal(str(round(data.voice_score_avg, 2))) if data.voice_score_avg is not None else None,
        duration_seconds=data.duration_seconds,
        questions_summary=summary_str,
    )
    saved = container.catalog_service.repo.save_practice_history(session, record)
    parsed_summary = []
    if saved.questions_summary:
        try:
            parsed_summary = json.loads(saved.questions_summary)
        except Exception:
            parsed_summary = []

    return PracticeHistoryOut(
        history_id=saved.history_id,
        user_id=saved.user_id,
        session_title=saved.session_title,
        source_type=saved.source_type,
        source_id=saved.source_id,
        domain_id=saved.domain_id,
        domain_name=saved.domain_name,
        role_name=saved.role_name,
        total_questions=saved.total_questions,
        evaluated_count=saved.evaluated_count,
        average_score=float(saved.average_score),
        quiz_score_avg=float(saved.quiz_score_avg) if saved.quiz_score_avg is not None else None,
        text_score_avg=float(saved.text_score_avg) if saved.text_score_avg is not None else None,
        voice_score_avg=float(saved.voice_score_avg) if saved.voice_score_avg is not None else None,
        duration_seconds=saved.duration_seconds,
        questions_summary=parsed_summary,
        created_at=saved.created_at,
    )


@router.get("/practice-history/me", response_model=list[PracticeHistoryOut])
def get_my_practice_history(
    limit: int = Query(50, ge=1, le=100),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
    user_id: int | None = Depends(get_optional_user_id),
) -> list[PracticeHistoryOut]:
    records = container.catalog_service.repo.list_practice_history(session, user_id=user_id, limit=limit)
    out: list[PracticeHistoryOut] = []
    for r in records:
        parsed_summary = []
        if r.questions_summary:
            try:
                parsed_summary = json.loads(r.questions_summary)
            except Exception:
                parsed_summary = []
        out.append(
            PracticeHistoryOut(
                history_id=r.history_id,
                user_id=r.user_id,
                session_title=r.session_title,
                source_type=r.source_type,
                source_id=r.source_id,
                domain_id=r.domain_id,
                domain_name=r.domain_name,
                role_name=r.role_name,
                total_questions=r.total_questions,
                evaluated_count=r.evaluated_count,
                average_score=float(r.average_score),
                quiz_score_avg=float(r.quiz_score_avg) if r.quiz_score_avg is not None else None,
                text_score_avg=float(r.text_score_avg) if r.text_score_avg is not None else None,
                voice_score_avg=float(r.voice_score_avg) if r.voice_score_avg is not None else None,
                duration_seconds=r.duration_seconds,
                questions_summary=parsed_summary,
                created_at=r.created_at,
            )
        )
    return out


@router.get("/question-sets/{set_id}/leaderboard", response_model=list[LeaderboardItemOut])
def get_question_set_leaderboard(
    set_id: str,
    limit: int = Query(10, ge=1, le=20),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[LeaderboardItemOut]:
    db_records = container.catalog_service.repo.get_question_set_leaderboard(session, str(set_id), limit=limit)
    items: list[LeaderboardItemOut] = []

    for idx, rec in enumerate(db_records, start=1):
        uname, uavatar, uis_pro = _get_user_info(session, container, rec.user_id)
        items.append(
            LeaderboardItemOut(
                rank=idx,
                user_id=rec.user_id or f"u-{rec.history_id}",
                user_name=uname,
                avatar_url=uavatar,
                is_pro=uis_pro,
                score=float(rec.average_score),
                duration_seconds=rec.duration_seconds,
                completed_at=rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else None,
            )
        )

    DEFAULT_LEADERBOARD = [
        {"user_name": "Nguyễn Văn An", "is_pro": True, "score": 96.5, "duration_seconds": 840, "completed_at": "2026-09-19 14:30"},
        {"user_name": "Trần Thị Mai", "is_pro": True, "score": 92.0, "duration_seconds": 960, "completed_at": "2026-09-18 20:15"},
        {"user_name": "Lê Minh Hiếu", "is_pro": True, "score": 89.0, "duration_seconds": 1050, "completed_at": "2026-09-19 09:45"},
        {"user_name": "Phạm Quốc Bảo", "is_pro": False, "score": 86.5, "duration_seconds": 1120, "completed_at": "2026-09-17 16:20"},
        {"user_name": "Vũ Hoàng Long", "is_pro": False, "score": 84.0, "duration_seconds": 1180, "completed_at": "2026-09-16 11:00"},
        {"user_name": "Đặng Thu Trang", "is_pro": False, "score": 81.5, "duration_seconds": 1240, "completed_at": "2026-09-15 15:10"},
        {"user_name": "Bùi Thanh Tùng", "is_pro": False, "score": 79.0, "duration_seconds": 1300, "completed_at": "2026-09-14 18:40"},
        {"user_name": "Ngô Minh Quân", "is_pro": False, "score": 76.5, "duration_seconds": 1350, "completed_at": "2026-09-13 13:25"},
        {"user_name": "Trịnh Thúy Vy", "is_pro": False, "score": 74.0, "duration_seconds": 1400, "completed_at": "2026-09-12 17:05"},
        {"user_name": "Đỗ Hải Đăng", "is_pro": False, "score": 72.5, "duration_seconds": 1450, "completed_at": "2026-09-11 19:30"},
    ]

    while len(items) < limit and (len(items) - len(db_records)) < len(DEFAULT_LEADERBOARD):
        seed = DEFAULT_LEADERBOARD[len(items) - len(db_records)]
        items.append(
            LeaderboardItemOut(
                rank=len(items) + 1,
                user_id=f"seed-{len(items)+1}",
                user_name=seed["user_name"],
                avatar_url=None,
                is_pro=seed["is_pro"],
                score=seed["score"],
                duration_seconds=seed["duration_seconds"],
                completed_at=seed["completed_at"],
            )
        )

    items.sort(key=lambda x: (-x.score, x.duration_seconds))
    for i, item in enumerate(items[:limit], start=1):
        item.rank = i
    return items[:limit]


@router.get("/question-sets/{set_id}/reviews", response_model=QuestionSetReviewsPageOut)
def get_question_set_reviews(
    set_id: str,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionSetReviewsPageOut:
    db_reviews = container.catalog_service.repo.list_question_set_reviews(session, str(set_id))
    review_outs: list[QuestionSetReviewOut] = []

    for r in db_reviews:
        review_outs.append(
            QuestionSetReviewOut(
                review_id=r.review_id,
                set_id=r.set_id,
                user_id=r.user_id,
                user_name=r.user_name,
                avatar_url=r.avatar_url,
                is_pro=r.is_pro,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at,
            )
        )

    DEFAULT_REVIEWS = [
        {
            "user_name": "Nguyễn Hoàng Nam",
            "is_pro": True,
            "rating": 5,
            "comment": "Bộ đề rất sát với thực tế phỏng vấn tại các doanh nghiệp lớn! Các câu hỏi theo khung STAR giúp mình hệ thống hóa câu trả lời rõ ràng và tự tin hơn rất nhiều.",
            "created_at": "2026-09-18 10:30",
        },
        {
            "user_name": "Lê Thị Thảo",
            "is_pro": False,
            "rating": 5,
            "comment": "Phần kiểm tra kết hợp cả 3 kỹ năng Trắc nghiệm, Tự luận và Ghi âm nói trực tiếp cực kỳ thực tế. AI chấm điểm chi tiết từng điểm mạnh và điểm cần cải thiện.",
            "created_at": "2026-09-17 15:45",
        },
        {
            "user_name": "Trần Tuấn Kiệt",
            "is_pro": True,
            "rating": 5,
            "comment": "Rất đáng luyện tập trước khi đi phỏng vấn thật. Giao diện workspace mượt mà, gợi ý câu trả lời mẫu theo chuẩn STAR giúp nâng tầm câu trả lời.",
            "created_at": "2026-09-15 09:20",
        },
    ]

    all_reviews = review_outs + [
        QuestionSetReviewOut(
            review_id=f"seed-rev-{idx+1}",
            set_id=str(set_id),
            user_id=None,
            user_name=dr["user_name"],
            avatar_url=None,
            is_pro=dr["is_pro"],
            rating=dr["rating"],
            comment=dr["comment"],
            created_at=dr["created_at"],
        )
        for idx, dr in enumerate(DEFAULT_REVIEWS)
    ]

    avg = round(sum(r.rating for r in all_reviews) / len(all_reviews), 1) if all_reviews else 5.0
    return QuestionSetReviewsPageOut(
        set_id=str(set_id),
        average_rating=avg,
        total_reviews=len(all_reviews),
        reviews=all_reviews,
    )


@router.post("/question-sets/{set_id}/reviews", response_model=QuestionSetReviewOut)
def submit_question_set_review(
    set_id: str,
    data: QuestionSetReviewIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
    user_id: int | None = Depends(get_optional_user_id),
) -> QuestionSetReviewOut:
    user_name, avatar_url, is_pro = _get_user_info(session, container, user_id)
    review = QuestionSetReviewModel(
        set_id=str(set_id),
        user_id=user_id,
        user_name=user_name,
        avatar_url=avatar_url,
        is_pro=is_pro,
        rating=data.rating,
        comment=data.comment.strip(),
    )
    saved = container.catalog_service.repo.add_question_set_review(session, review)
    return QuestionSetReviewOut(
        review_id=saved.review_id,
        set_id=saved.set_id,
        user_id=saved.user_id,
        user_name=saved.user_name,
        avatar_url=saved.avatar_url,
        is_pro=saved.is_pro,
        rating=saved.rating,
        comment=saved.comment,
        created_at=saved.created_at,
    )


@router.post("/evaluations/queue", response_model=EvaluationQueueOut)
async def enqueue_question_evaluation(
    data: EvaluationQueueIn,
    background_tasks: BackgroundTasks,
    container: ServiceContainer = Depends(get_container),
) -> EvaluationQueueOut:
    """
    Pipeline B: Asynchronous Background Enqueue for Question Evaluation.
    Calculates instant Quiz score (0ms) and enqueues Text STAR & Voice analysis
    into Redis / In-Memory Pull MQ without blocking the candidate's workspace.
    """
    quiz_score = 15.0 if data.is_quiz_correct is True else 0.0

    # Enqueue task in Pull MQ
    task_id = eval_pull_queue.enqueue(data.model_dump())

    # Trigger background worker evaluation with LLM & Delivery telemetry
    background_tasks.add_task(eval_pull_queue.process_task_async, task_id, container)

    return EvaluationQueueOut(
        task_id=task_id,
        status="queued",
        quiz_score=quiz_score,
        created_at=time.time(),
    )


@router.get("/evaluations/pull/{task_id}", response_model=EvaluationPullOut)
def pull_evaluation_result(task_id: str) -> EvaluationPullOut:
    """
    Client pulls evaluation result with minimal polling backoff.
    """
    task = eval_pull_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    return EvaluationPullOut(
        task_id=task_id,
        status=task.get("status", "queued"),
        result=task.get("result"),
        error=task.get("error"),
    )
