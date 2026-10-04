from __future__ import annotations

import logging
from typing import Any
import uuid

from sqlalchemy.orm import sessionmaker

from ...domain.errors import DomainValidationError
from ...domain.jd_interview import (
    InterviewBlueprint,
    InterviewScript,
    JDJobStatus,
    JDSourceType,
    JobAnalysis,
    NormalizedJD,
)
from ...infrastructure.persistence.models.jd_interview import (
    InterviewBlueprintRecord,
    InterviewScriptRecord,
    JDGenerationJob,
    JobAnalysisRecord,
    NormalizedJDRecord,
)
from ...infrastructure.queue.jd_queue import JDQueueManager
from .analyzer_service import InterviewPlannerService, JDAnalyzerService
from .ingestion_service import FileIngestionService, TextNormalizer, UrlIngestionService
from .question_generator import ParallelQuestionGenerator, QuestionAggregator, QualityGateValidator

logger = logging.getLogger(__name__)


class JDWorkflowOrchestrator:
    def __init__(
        self,
        session_factory: sessionmaker,
        analyzer: JDAnalyzerService,
        question_generator: ParallelQuestionGenerator,
        queue_manager: JDQueueManager | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.analyzer = analyzer
        self.question_generator = question_generator
        self.queue_manager = queue_manager or JDQueueManager()

    def _persist_job_state(
        self,
        job_id: str,
        status: JDJobStatus,
        stage: str,
        progress_pct: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        # 1. Update fast queue cache
        self.queue_manager.update_job_progress(
            job_id=job_id,
            status=status.value,
            stage=stage,
            progress_pct=progress_pct,
            error=error_message,
        )

        # 2. Update relational database
        try:
            with self.session_factory() as session:
                record = session.get(JDGenerationJob, job_id)
                if record:
                    record.status = status.value
                    record.stage = stage
                    record.progress_pct = progress_pct
                    record.error_code = error_code
                    record.error_message = error_message
                    session.commit()
        except Exception as exc:
            logger.error("Failed to persist job status to DB: %s", exc)

    async def execute_pipeline(
        self,
        job_id: str,
        user_id: int,
        source_type: str,
        input_data: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        duration_minutes = options.get("duration_minutes", 45)
        custom_difficulty = options.get("difficulty")
        language = options.get("language", "vi")

        try:
            # ----------------------------------------------------
            # STAGE 1: INGESTION (Progress 10%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.INGESTING, "Đang xử lý nội dung Job Description...", 10)

            normalized_jd: NormalizedJD
            if source_type == JDSourceType.file.value:
                filename = input_data.get("filename", "uploaded_jd.txt")
                content = input_data.get("content", b"")
                normalized_jd = FileIngestionService.ingest_file(filename, content)
            elif source_type == JDSourceType.url.value:
                url_str = input_data.get("url", "")
                normalized_jd = await UrlIngestionService.ingest_url(url_str)
            else:
                raw_text = input_data.get("text", "")
                normalized_jd = TextNormalizer.create_normalized_jd(JDSourceType.text, raw_text)

            # Persist Normalized JD
            with self.session_factory() as session:
                norm_rec = NormalizedJDRecord(
                    job_id=job_id,
                    source_type=normalized_jd.source_type,
                    original_filename=normalized_jd.original_filename,
                    original_url=normalized_jd.original_url,
                    checksum=normalized_jd.checksum,
                    raw_content=normalized_jd.raw_content,
                    cleaned_text=normalized_jd.cleaned_text,
                    language=normalized_jd.language,
                    warnings=normalized_jd.warnings,
                )
                session.add(norm_rec)
                session.commit()

            # ----------------------------------------------------
            # STAGE 2: NORMALIZED & CHECKSUM CHECK (Progress 25%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.NORMALIZED, "Đã chuẩn hóa và kiểm tra checksum...", 25)

            # ----------------------------------------------------
            # STAGE 3: JD ANALYSIS (Progress 45%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.ANALYZING, "Đang phân tích cấu trúc năng lực và kỹ năng từ JD...", 45)
            analysis: JobAnalysis = await self.analyzer.analyze(normalized_jd)

            # Persist Job Analysis
            with self.session_factory() as session:
                analysis_rec = JobAnalysisRecord(
                    job_id=job_id,
                    job_title=analysis.job_title,
                    company_name=analysis.company_name,
                    seniority=analysis.seniority,
                    employment_type=analysis.employment_type,
                    location=analysis.location,
                    responsibilities=analysis.responsibilities,
                    required_skills=analysis.required_skills,
                    preferred_skills=analysis.preferred_skills,
                    technologies=analysis.technologies,
                    domain_knowledge=analysis.domain_knowledge,
                    soft_skills=analysis.soft_skills,
                    technical_signals=analysis.technical_signals,
                    behavioral_signals=analysis.behavioral_signals,
                    confidence_score=analysis.confidence_score,
                )
                session.add(analysis_rec)
                session.commit()

            # ----------------------------------------------------
            # STAGE 4: BLUEPRINT PLANNING (Progress 65%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.PLANNING, "Đang lập Interview Blueprint & phân bổ phần thi...", 65)
            blueprint: InterviewBlueprint = InterviewPlannerService.build_blueprint(
                analysis=analysis,
                total_duration_minutes=duration_minutes,
                target_difficulty=custom_difficulty,
            )

            # Persist Blueprint
            with self.session_factory() as session:
                bp_rec = InterviewBlueprintRecord(
                    job_id=job_id,
                    target_role=blueprint.target_role,
                    seniority=blueprint.seniority,
                    total_duration_minutes=blueprint.total_duration_minutes,
                    target_difficulty=blueprint.target_difficulty,
                    objectives=blueprint.objectives,
                    competencies=blueprint.competencies,
                    sections=[
                        {
                            "section_type": s.section_type,
                            "allocated_minutes": s.allocated_minutes,
                            "target_competencies": s.target_competencies,
                            "question_count": s.question_count,
                            "objective": s.objective,
                        }
                        for s in blueprint.sections
                    ],
                    scoring_dimensions=blueprint.scoring_dimensions,
                )
                session.add(bp_rec)
                session.commit()

            # ----------------------------------------------------
            # STAGE 5: QUESTION GENERATION (Progress 85%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.GENERATING, "Đang sinh câu hỏi, gợi ý STAR và follow-up probes song song...", 85)
            raw_items = await self.question_generator.generate_all_questions_parallel(
                blueprint=blueprint,
                analysis=analysis,
                language=language,
            )

            # ----------------------------------------------------
            # STAGE 6: AGGREGATE & VALIDATE (Progress 95%)
            # ----------------------------------------------------
            self._persist_job_state(job_id, JDJobStatus.VALIDATING, "Đang lọc trùng lặp và kiểm tra độ phủ kỹ năng...", 95)
            script: InterviewScript = QuestionAggregator.aggregate_and_deduplicate(raw_items, blueprint)
            passed, warnings = QualityGateValidator.validate_script(script, analysis)

            # Persist Final Script
            serialized_items = [
                {
                    "order_index": item.order_index,
                    "section_type": item.section_type,
                    "competency_name": item.competency_name,
                    "question_text": item.question_text,
                    "rationale": item.rationale,
                    "difficulty": item.difficulty,
                    "expected_signals": item.expected_signals,
                    "red_flags": item.red_flags,
                    "sample_good_answer": item.sample_good_answer,
                    "follow_up_probes": item.follow_up_probes,
                }
                for item in script.items
            ]

            with self.session_factory() as session:
                script_rec = InterviewScriptRecord(
                    job_id=job_id,
                    script_id=script.script_id,
                    total_questions=script.total_questions,
                    estimated_minutes=script.estimated_minutes,
                    items=serialized_items,
                )
                session.add(script_rec)
                session.commit()

            # ----------------------------------------------------
            # STAGE 7: COMPLETED (Progress 100%)
            # ----------------------------------------------------
            result_payload = {
                "script_id": script.script_id,
                "job_id": job_id,
                "role": blueprint.target_role,
                "seniority": blueprint.seniority,
                "company_name": blueprint.company_name,
                "focus_areas": blueprint.focus_areas,
                "total_questions": script.total_questions,
                "estimated_minutes": script.estimated_minutes,
                "questions": serialized_items,
                "warnings": warnings,
            }

            self.queue_manager.update_job_progress(
                job_id=job_id,
                status=JDJobStatus.COMPLETED.value,
                stage="Kịch bản phỏng vấn đã sẵn sàng!",
                progress_pct=100,
                result=result_payload,
            )

            with self.session_factory() as session:
                job_rec = session.get(JDGenerationJob, job_id)
                if job_rec:
                    job_rec.status = JDJobStatus.COMPLETED.value
                    job_rec.stage = "COMPLETED"
                    job_rec.progress_pct = 100
                    session.commit()

            return result_payload

        except DomainValidationError as exc:
            logger.warning("Domain validation error in workflow: %s", exc)
            self._persist_job_state(
                job_id,
                JDJobStatus.FAILED,
                "Lỗi dữ liệu đầu vào",
                100,
                error_code="VALIDATION_ERROR",
                error_message=str(exc),
            )
            self.queue_manager.push_to_dlq(job_id, {"error": str(exc), "stage": "VALIDATION"})
            raise

        except Exception as exc:
            logger.exception("Unexpected error during JD workflow: %s", exc)
            self._persist_job_state(
                job_id,
                JDJobStatus.FAILED,
                "Lỗi xử lý nội bộ",
                100,
                error_code="INTERNAL_ERROR",
                error_message="Có lỗi xảy ra khi tạo kịch bản phỏng vấn. Vui lòng thử lại sau.",
            )
            self.queue_manager.push_to_dlq(job_id, {"error": str(exc), "stage": "EXECUTION"})
            raise
