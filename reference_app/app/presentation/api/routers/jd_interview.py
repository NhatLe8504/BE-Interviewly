from __future__ import annotations

import asyncio
import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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
from ..dependencies import get_container, get_optional_user_id, get_session
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


def _init_job(session: Session, user_id: int, source_type: str, checksum: str) -> str:
    job_id = f"jd_{uuid.uuid4().hex[:12]}"
    job = JDGenerationJob(
        job_id=job_id,
        user_id=user_id,
        source_type=source_type,
        checksum=checksum,
        status=JDJobStatus.PENDING.value,
        stage="INITIALIZED",
        progress_pct=5,
    )
    session.add(job)
    session.commit()
    return job_id


@router.post("/text", response_model=JDJobStatusOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_jd_text(
    payload: JDTextSubmissionIn,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    effective_user_id = user_id if user_id and user_id > 0 else 1
    checksum = NormalizedJD.calculate_checksum(payload.text)
    job_id = _init_job(session, effective_user_id, JDSourceType.text.value, checksum)

    orchestrator = _get_or_create_orchestrator(container)
    orchestrator.queue_manager.enqueue(
        job_id=job_id,
        payload={"source_type": "text", "text_length": len(payload.text)},
    )

    asyncio.create_task(
        orchestrator.execute_pipeline(
            job_id=job_id,
            user_id=effective_user_id,
            source_type=JDSourceType.text.value,
            input_data={"text": payload.text},
            options={
                "duration_minutes": payload.duration_minutes,
                "difficulty": payload.difficulty,
                "language": payload.language,
            },
        )
    )

    return JDJobStatusOut(
        job_id=job_id,
        status="PENDING",
        stage="Đã tiếp nhận yêu cầu phân tích JD...",
        progress_pct=5,
    )


@router.post("/url", response_model=JDJobStatusOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_jd_url(
    payload: JDUrlSubmissionIn,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    effective_user_id = user_id if user_id and user_id > 0 else 1
    checksum = NormalizedJD.calculate_checksum(payload.url)
    job_id = _init_job(session, effective_user_id, JDSourceType.url.value, checksum)

    orchestrator = _get_or_create_orchestrator(container)
    orchestrator.queue_manager.enqueue(
        job_id=job_id,
        payload={"source_type": "url", "url": payload.url},
    )

    asyncio.create_task(
        orchestrator.execute_pipeline(
            job_id=job_id,
            user_id=effective_user_id,
            source_type=JDSourceType.url.value,
            input_data={"url": payload.url},
            options={
                "duration_minutes": payload.duration_minutes,
                "difficulty": payload.difficulty,
                "language": payload.language,
            },
        )
    )

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
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    effective_user_id = user_id if user_id and user_id > 0 else 1
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Tệp tải lên không có dữ liệu")

    checksum = NormalizedJD.calculate_checksum(file.filename or "file")
    job_id = _init_job(session, effective_user_id, JDSourceType.file.value, checksum)

    orchestrator = _get_or_create_orchestrator(container)
    orchestrator.queue_manager.enqueue(
        job_id=job_id,
        payload={"source_type": "file", "filename": file.filename},
    )

    asyncio.create_task(
        orchestrator.execute_pipeline(
            job_id=job_id,
            user_id=effective_user_id,
            source_type=JDSourceType.file.value,
            input_data={"filename": file.filename, "content": content},
            options={
                "duration_minutes": duration_minutes,
                "difficulty": difficulty,
                "language": language,
            },
        )
    )

    return JDJobStatusOut(
        job_id=job_id,
        status="PENDING",
        stage="Đã nhận tệp tài liệu JD, chuẩn bị giải mã văn bản...",
        progress_pct=5,
    )


@router.get("/my-jobs", response_model=list[JDJobSummaryOut])
def get_my_jd_jobs(
    limit: int = 30,
    offset: int = 0,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
) -> list[JDJobSummaryOut]:
    effective_user_id = user_id if user_id and user_id > 0 else 1
    query = (
        session.query(JDGenerationJob)
        .filter(JDGenerationJob.user_id == effective_user_id)
        .order_by(JDGenerationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    jobs = query.all()
    if not jobs:
        jobs = (
            session.query(JDGenerationJob)
            .order_by(JDGenerationJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    summaries: list[JDJobSummaryOut] = []
    for job in jobs:
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

        summaries.append(
            JDJobSummaryOut(
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
                error=job.error_message,
            )
        )
    return summaries


@router.get("/jobs/{job_id}/status", response_model=JDJobStatusOut)
def get_job_status(
    job_id: str,
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JDJobStatusOut:
    orchestrator = _get_or_create_orchestrator(container)
    queue_state = orchestrator.queue_manager.get_job_state(job_id)

    if queue_state:
        res = queue_state.get("result")
        return JDJobStatusOut(
            job_id=job_id,
            status=queue_state.get("status", "PENDING"),
            stage=queue_state.get("stage", "Đang xử lý..."),
            progress_pct=queue_state.get("progress_pct", 0),
            result=res,
            error=queue_state.get("error"),
        )

    # Fallback to DB
    job_record = session.get(JDGenerationJob, job_id)
    if not job_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin tiến trình JD này")

    result = None
    if job_record.status == JDJobStatus.COMPLETED.value:
        script_rec = session.query(InterviewScriptRecord).filter_by(job_id=job_id).first()
        bp_rec = session.query(InterviewBlueprintRecord).filter_by(job_id=job_id).first()
        if script_rec and bp_rec:
            company_name = job_record.analysis.company_name if job_record.analysis else ""
            result = {
                "script_id": script_rec.script_id,
                "job_id": job_id,
                "role": bp_rec.target_role,
                "seniority": bp_rec.seniority,
                "company_name": company_name or "",
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
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    job_record = session.get(JDGenerationJob, job_id)
    if not job_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình tạo phỏng vấn")

    if job_record.status != JDJobStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Kịch bản phỏng vấn chưa hoàn tất, vui lòng chờ trong giây lát")

    script_rec = session.query(InterviewScriptRecord).filter_by(job_id=job_id).first()
    bp_rec = session.query(InterviewBlueprintRecord).filter_by(job_id=job_id).first()
    if not script_rec or not bp_rec or not script_rec.items:
        raise HTTPException(status_code=400, detail="Dữ liệu kịch bản không hợp lệ")

    effective_user_id = user_id if user_id and user_id > 0 else job_record.user_id

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

    first_turn = OrmInterviewTurn(
        session_id=orm_session.session_id,
        turn_number=1,
        speaker=TurnSpeaker.ai,
        message_text=first_q_text,
    )
    session.add(first_turn)
    session.flush()

    job_record.session_id = orm_session.session_id
    session.commit()

    company_name = job_record.analysis.company_name if job_record.analysis else ""
    return {
        "session_id": orm_session.session_id,
        "first_question": first_q_text,
        "script_id": script_rec.script_id,
        "role": bp_rec.target_role,
        "seniority": bp_rec.seniority,
        "company_name": company_name or "",
        "focus_areas": bp_rec.competencies or [],
        "total_questions": script_rec.total_questions,
        "estimated_minutes": script_rec.estimated_minutes,
        "all_questions": [item["question_text"] for item in script_rec.items],
    }