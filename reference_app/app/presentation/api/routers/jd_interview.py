from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ....application.interview.commands import StartSessionCommand
from ....domain.errors import DomainValidationError
from ....domain.jd_interview import JDJobStatus, JDSourceType, NormalizedJD
from ....infrastructure.persistence.models.jd_interview import (
    InterviewBlueprintRecord,
    InterviewScriptRecord,
    JDGenerationJob,
    JobAnalysisRecord,
    NormalizedJDRecord,
)
from ..dependencies import get_container, get_current_user_id, get_optional_user_id, get_session
from ..schemas.jd_interview import (
    JDJobStatusOut,
    JDJobSummaryOut,
    JDStartSessionIn,
    JDTextSubmissionIn,
    JDUrlSubmissionIn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/interviews/from-jd", tags=["jd-interviews"])


def _get_or_create_orchestrator(container: ServiceContainer):
    if hasattr(container, "jd_orchestrator") and container.jd_orchestrator is not None:
        return container.jd_orchestrator

    from ....application.jd_interview.analyzer_service import JDAnalyzerService
    from ....application.jd_interview.orchestrator import JDWorkflowOrchestrator
    from ....application.jd_interview.question_generator import ParallelQuestionGenerator
    from ....infrastructure.queue.jd_queue import JDQueueManager

    api_key = container.settings.groq_api_key if hasattr(container.settings, "groq_api_key") else ""
    if not api_key:
        import os
        api_key = os.environ.get("GROQ_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")

    analyzer = JDAnalyzerService(api_key=api_key)
    generator = ParallelQuestionGenerator(api_key=api_key)
    queue_mgr = JDQueueManager(redis_client=container.redis_client)

    orchestrator = JDWorkflowOrchestrator(
        session_factory=container.session_factory,
        analyzer=analyzer,
        question_generator=generator,
        queue_manager=queue_mgr,
    )
    container.jd_orchestrator = orchestrator
    container.jd_queue_manager = queue_mgr
    return orchestrator


def _init_job(session: Session, user_id: int, source_type: str, checksum: str, request_payload: dict[str, Any], is_public: bool = False) -> str:
    job_id = f"jd_{uuid.uuid4().hex[:12]}"
    job = JDGenerationJob(
        job_id=job_id,
        user_id=user_id,
        source_type=source_type,
        checksum=checksum,
        status=JDJobStatus.PENDING.value,
        stage="INITIALIZED",
        progress_pct=5,
        request_payload=request_payload,
        is_public=is_public,
    )
    session.add(job)
    session.commit()
    return job_id


_running_jobs: dict[str, asyncio.Task] = {}


def schedule_jd_job(container: ServiceContainer, job_id: str) -> None:
    if job_id in _running_jobs:
        return

    async def run() -> None:
        orchestrator = _get_or_create_orchestrator(container)
        with container.session_factory() as session:
            job = session.get(JDGenerationJob, job_id)
            if job is None or job.status == JDJobStatus.COMPLETED.value:
                return
            payload = job.request_payload
            user_id, source_type = job.user_id, job.source_type
        if not payload:
            return
        lock_connection = None
        try:
            engine = container.session_factory.kw["bind"]
            if engine.dialect.name == "postgresql":
                lock_connection = engine.connect()
                locked = lock_connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:job_id))"), {"job_id": job_id}
                ).scalar()
                if not locked:
                    return
            with container.session_factory() as session:
                job = session.get(JDGenerationJob, job_id)
                if job is None or job.status == JDJobStatus.COMPLETED.value:
                    return
                for child in (job.script, job.blueprint, job.analysis, job.normalized_jd):
                    if child is not None:
                        session.delete(child)
                job.status = JDJobStatus.PENDING.value
                job.stage = "INITIALIZED"
                job.progress_pct = 5
                session.commit()
            input_data = payload["input_data"]
            if source_type == JDSourceType.file.value:
                input_data = {**input_data, "content": base64.b64decode(input_data["content_base64"])}
                del input_data["content_base64"]
            await orchestrator.execute_pipeline(job_id, user_id, source_type, input_data, payload["options"])
        except Exception:
            logger.exception("JD job %s could not start; rolling back", job_id)
            with container.session_factory() as session:
                job = session.get(JDGenerationJob, job_id)
                if job is not None and job.status != JDJobStatus.COMPLETED.value:
                    session.delete(job)
                    session.commit()
            orchestrator.queue_manager.remove_job(job_id)
        finally:
            if lock_connection is not None:
                lock_connection.execute(text("SELECT pg_advisory_unlock(hashtext(:job_id))"), {"job_id": job_id})
                lock_connection.close()

    task = asyncio.create_task(run())
    _running_jobs[job_id] = task
    task.add_done_callback(lambda done: (_running_jobs.pop(job_id, None), done.exception() if not done.cancelled() else None))


@router.post("/text", response_model=JDJobStatusOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_jd_text(
    payload: JDTextSubmissionIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    request_payload = {"input_data": {"text": payload.text}, "options": {"duration_minutes": payload.duration_minutes, "difficulty": payload.difficulty, "language": payload.language}}
    job_id = _init_job(session, user_id, JDSourceType.text.value,
                       NormalizedJD.calculate_checksum(payload.text), request_payload, is_public=payload.is_public)
    schedule_jd_job(container, job_id)

    return JDJobStatusOut(
        job_id=job_id,
        status="PENDING",
        stage="Đã tiếp nhận yêu cầu phân tích JD...",
        progress_pct=5,
    )


@router.post("/url", response_model=JDJobStatusOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_jd_url(
    payload: JDUrlSubmissionIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    request_payload = {"input_data": {"url": payload.url}, "options": {"duration_minutes": payload.duration_minutes, "difficulty": payload.difficulty, "language": payload.language}}
    job_id = _init_job(session, user_id, JDSourceType.url.value,
                       NormalizedJD.calculate_checksum(payload.url), request_payload, is_public=payload.is_public)
    schedule_jd_job(container, job_id)

    return JDJobStatusOut(
        job_id=job_id,
        status="PENDING",
        stage="Đã tiếp nhận đường dẫn JD, chuẩn bị tải nội dung...",
        progress_pct=5,
    )


@router.post("/file", response_model=JDJobStatusOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_jd_file(
    file: UploadFile = File(...),
    duration_minutes: int = Form(45),
    difficulty: int | None = Form(None),
    language: str = Form("vi"),
    is_public: bool = Form(False),
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Tệp tải lên không có dữ liệu")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Tệp JD vượt quá 5 MB")
    request_payload = {
        "input_data": {"filename": file.filename, "content_base64": base64.b64encode(content).decode("ascii")},
        "options": {"duration_minutes": duration_minutes, "difficulty": difficulty, "language": language},
    }
    job_id = _init_job(session, user_id, JDSourceType.file.value,
                       NormalizedJD.calculate_checksum(content.hex()), request_payload, is_public=is_public)
    schedule_jd_job(container, job_id)

    return JDJobStatusOut(
        job_id=job_id,
        status="PENDING",
        stage="Đã nhận tệp tài liệu JD, chuẩn bị giải mã văn bản...",
        progress_pct=5,
    )


def _resolve_linked_job(session: Session, job: JDGenerationJob) -> tuple[Any | None, bool]:
    """
    Tìm JobPostingRecord liên kết từ JDGenerationJob.
    Trả về (posting_record, is_custom_jd)
    """
    from ....infrastructure.persistence.models.job_aggregator import JobPostingRecord, JobCompanyRecord

    # 1. Check normalized_jd.original_url (e.g. job:xxx)
    if job.normalized_jd and job.normalized_jd.original_url:
        url = job.normalized_jd.original_url.strip()
        if url.startswith("job:"):
            job_post_id = url[4:].strip()
            posting = session.get(JobPostingRecord, job_post_id)
            if posting:
                return posting, False

    # 2. Check checksum match with job_postings
    if job.checksum:
        posting = (
            session.query(JobPostingRecord)
            .filter(JobPostingRecord.content_fingerprint == job.checksum)
            .first()
        )
        if posting:
            return posting, False

    # 3. Fallback: match by title and company if analysis exists
    if job.analysis and job.analysis.job_title and job.analysis.company_name:
        clean_comp = job.analysis.company_name.strip()
        if clean_comp:
            posting = (
                session.query(JobPostingRecord)
                .join(JobCompanyRecord, JobCompanyRecord.company_id == JobPostingRecord.company_id)
                .filter(
                    JobPostingRecord.title == job.analysis.job_title,
                    JobCompanyRecord.company_name.ilike(f"%{clean_comp}%"),
                )
                .first()
            )
            if posting:
                return posting, False

    return None, True


def _format_job_summary(job: JDGenerationJob, session: Session | None = None) -> JDJobSummaryOut:
    role = "Software Engineer"
    seniority = "junior"
    company = ""
    focus_areas: list[str] = []
    total_questions = 0
    estimated_minutes = 45

    if job.analysis:
        role = job.analysis.job_title or role
        seniority = job.analysis.seniority or seniority
        company = job.analysis.company_name or ""
        focus_areas = job.analysis.required_skills or []

    if job.blueprint:
        role = job.blueprint.target_role or role
        seniority = job.blueprint.seniority or seniority
        if job.blueprint.competencies:
            focus_areas = job.blueprint.competencies
        if job.blueprint.total_duration_minutes:
            estimated_minutes = job.blueprint.total_duration_minutes

    if job.script:
        total_questions = job.script.total_questions
        estimated_minutes = job.script.estimated_minutes

    origin_job_id = None
    company_logo_url = None
    company_banner_url = None
    skills: list[str] = []
    is_custom_jd = True

    if session:
        posting, is_custom = _resolve_linked_job(session, job)
        is_custom_jd = is_custom
        if posting:
            origin_job_id = posting.job_id
            if posting.company:
                company_logo_url = posting.company.logo_url
                company_banner_url = posting.company.banner_url
                if not company and posting.company.company_name:
                    company = posting.company.company_name
            skills = posting.skills_required or posting.technologies or []

    if not skills:
        skills = focus_areas

    return JDJobSummaryOut(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        progress_pct=job.progress_pct,
        source_type=job.source_type,
        role=role,
        seniority=seniority,
        company_name=company,
        focus_areas=focus_areas,
        total_questions=total_questions,
        estimated_minutes=estimated_minutes,
        session_id=job.session_id,
        created_at=job.created_at.isoformat() if job.created_at else None,
        is_public=bool(getattr(job, "is_public", False)),
        error=job.error_message,
        origin_job_id=origin_job_id,
        company_logo_url=company_logo_url,
        company_banner_url=company_banner_url,
        skills=skills,
        is_custom_jd=is_custom_jd,
    )


@router.get("/community-jobs", response_model=list[JDJobSummaryOut])
def get_community_jd_jobs(
    limit: int = 30,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[JDJobSummaryOut]:
    """Lấy danh sách các bộ đề JD đã tạo thành công và được chia sẻ công khai bởi cộng đồng."""
    query = (
        session.query(JDGenerationJob)
        .filter(
            JDGenerationJob.is_public.is_(True),
            JDGenerationJob.status == JDJobStatus.COMPLETED.value,
        )
        .order_by(JDGenerationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    jobs = query.all()
    return [_format_job_summary(job, session=session) for job in jobs]


@router.get("/notifications")
def unread_jd_notifications(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> list[dict[str, str]]:
    jobs = session.query(JDGenerationJob).filter(
        JDGenerationJob.user_id == user_id,
        JDGenerationJob.status == JDJobStatus.COMPLETED.value,
        JDGenerationJob.notification_pending.is_(True),
    ).order_by(JDGenerationJob.created_at.desc()).limit(20).all()
    return [{"job_id": job.job_id, "message": "Buổi phỏng vấn từ JD đã sẵn sàng"} for job in jobs]


@router.post("/jobs/{job_id}/notification-read", status_code=204)
def acknowledge_jd_notification(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> None:
    job = session.get(JDGenerationJob, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
    if job.status != JDJobStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="Buổi phỏng vấn chưa sẵn sàng")
    job.notification_pending = False
    session.commit()


@router.get("/my-jobs", response_model=list[JDJobSummaryOut])
def get_my_jd_jobs(
    limit: int = 30,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> list[JDJobSummaryOut]:
    query = (
        session.query(JDGenerationJob)
        .filter(JDGenerationJob.user_id == user_id)
        .order_by(JDGenerationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    jobs = query.all()
    if not jobs:
        return []

    return [_format_job_summary(job, session=session) for job in jobs]


@router.get("/jobs/{job_id}/status", response_model=JDJobStatusOut)
def get_job_status(
    job_id: str,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    job_record = session.get(JDGenerationJob, job_id)
    if not job_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin tiến trình JD này")

    # Private job privacy protection: enforce owner or admin access
    if not bool(getattr(job_record, "is_public", False)):
        if not user_id:
            raise HTTPException(status_code=401, detail="Vui lòng đăng nhập để xem tiến trình JD này")
        if job_record.user_id != user_id:
            try:
                user = container.auth_service.get_user(session, user_id)
                if getattr(user, "role", None) != "admin":
                    raise HTTPException(status_code=403, detail="Forbidden: You do not own this JD interview job")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="Forbidden: You do not own this JD interview job")

    orchestrator = _get_or_create_orchestrator(container)
    queue_state = orchestrator.queue_manager.get_job_state(job_id)
    if queue_state and job_record.status != JDJobStatus.COMPLETED.value:
        res = queue_state.get("result")
        return JDJobStatusOut(
            job_id=job_id,
            status=queue_state.get("status", "PENDING"),
            stage=queue_state.get("stage", "Đang xử lý..."),
            progress_pct=queue_state.get("progress_pct", 0),
            result=res,
            error=queue_state.get("error"),
        )

    result = None
    if job_record.status == JDJobStatus.COMPLETED.value:
        script_rec = session.query(InterviewScriptRecord).filter_by(job_id=job_id).first()
        bp_rec = session.query(InterviewBlueprintRecord).filter_by(job_id=job_id).first()
        if script_rec and bp_rec:
            company_name = job_record.analysis.company_name if job_record.analysis else ""
            posting, is_custom_jd = _resolve_linked_job(session, job_record)
            origin_job_id = posting.job_id if posting else None
            company_logo_url = posting.company.logo_url if (posting and posting.company) else None
            company_banner_url = posting.company.banner_url if (posting and posting.company) else None
            if posting and posting.company and not company_name:
                company_name = posting.company.company_name
            skills = (posting.skills_required or posting.technologies) if posting else (bp_rec.competencies or [])

            result = {
                "script_id": script_rec.script_id,
                "job_id": job_id,
                "role": bp_rec.target_role,
                "seniority": bp_rec.seniority,
                "company_name": company_name or "",
                "company_logo_url": company_logo_url,
                "company_banner_url": company_banner_url,
                "origin_job_id": origin_job_id,
                "skills": skills,
                "is_custom_jd": is_custom_jd,
                "focus_areas": bp_rec.competencies or [],
                "total_questions": script_rec.total_questions,
                "estimated_minutes": script_rec.estimated_minutes,
                "questions": script_rec.items,
                "warnings": [],
            }

    return JDJobStatusOut(
        job_id=job_id,
        status=job_record.status,
        stage=job_record.stage,
        progress_pct=job_record.progress_pct,
        result=result,
        error=job_record.error_message,
    )


@router.post("/jobs/{job_id}/start-session")
def start_interview_from_jd_job(
    job_id: str,
    payload: JDStartSessionIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    job_record = session.get(JDGenerationJob, job_id)
    if not job_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình tạo phỏng vấn")

    if not bool(getattr(job_record, "is_public", False)) and job_record.user_id != user_id:
        try:
            user = container.auth_service.get_user(session, user_id)
            if getattr(user, "role", None) != "admin":
                raise HTTPException(status_code=403, detail="Forbidden: You do not own this JD interview job")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="Forbidden: You do not own this JD interview job")

    if job_record.status != JDJobStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Kịch bản phỏng vấn chưa hoàn tất, vui lòng chờ trong giây lát")

    script_rec = session.query(InterviewScriptRecord).filter_by(job_id=job_id).first()
    bp_rec = session.query(InterviewBlueprintRecord).filter_by(job_id=job_id).first()
    if not script_rec or not bp_rec or not script_rec.items:
        raise HTTPException(status_code=400, detail="Dữ liệu kịch bản không hợp lệ")

    effective_user_id = user_id

    from ....infrastructure.persistence.models.session import InterviewSession as OrmInterviewSession, InterviewTurn as OrmInterviewTurn
    from ....infrastructure.persistence.models.enums import ExperienceLevel, Language, SessionMode, SessionStatus, TurnSpeaker

    first_q_text = script_rec.items[0]["question_text"]
    seniority_val = bp_rec.seniority if bp_rec.seniority in ("intern", "fresher", "junior", "mid", "senior") else "junior"

    orm_session = OrmInterviewSession(
        candidate_id=effective_user_id,
        domain_id=None,
        role_id=None,
        experience_level=ExperienceLevel(seniority_val),
        language=Language.vi,
        mode=SessionMode(payload.mode) if payload.mode in ("text", "voice") else SessionMode.text,
        barge_in_enabled=payload.barge_in_enabled,
        status=SessionStatus.in_progress,
    )
    session.add(orm_session)
    session.flush()

    job_record.session_id = orm_session.session_id
    session.commit()

    posting, is_custom_jd = _resolve_linked_job(session, job_record)
    origin_job_id = posting.job_id if posting else None
    company_logo_url = posting.company.logo_url if (posting and posting.company) else None
    company_name = job_record.analysis.company_name if job_record.analysis else ""
    if posting and posting.company and not company_name:
        company_name = posting.company.company_name

    return {
        "session_id": orm_session.session_id,
        "first_question": first_q_text,
        "script_id": script_rec.script_id,
        "role": bp_rec.target_role,
        "seniority": bp_rec.seniority,
        "company_name": company_name or "",
        "company_logo_url": company_logo_url,
        "origin_job_id": origin_job_id,
        "is_custom_jd": is_custom_jd,
        "focus_areas": bp_rec.competencies or [],
        "total_questions": script_rec.total_questions,
        "estimated_minutes": script_rec.estimated_minutes,
        "all_questions": [item["question_text"] for item in script_rec.items],
    }