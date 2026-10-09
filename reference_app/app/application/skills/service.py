from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.persistence.models.catalog import PracticeHistoryRecord, QuestionBank
from ...infrastructure.persistence.models.job_aggregator import JobPostingRecord
from ...infrastructure.persistence.models.session import InterviewSession, InterviewTurn
from ...infrastructure.persistence.models.user_skills import (
    JobReadinessRecord,
    UserCareerProfileRecord,
    UserSkillEvidenceRecord,
    UserSkillLevelRecord,
)
from ...infrastructure.persistence.practice_evaluation_repository import (
    PART_VOICE,
    fetch_practice_evaluations_by_ids,
)
from .estimator import EvidenceInput, SkillEstimateResult, SkillLevelEstimator
from .readiness import JobReadinessAssessment, JobReadinessEvaluator, JobRequirementItem
from .taxonomy import get_default_taxonomy

logger = logging.getLogger(__name__)


class UserSkillService:
    def __init__(self, session: Session, jev_adapter: Any = None) -> None:
        self.session = session
        self.taxonomy = get_default_taxonomy()
        if jev_adapter is None:
            try:
                from ...infrastructure.llm.jev_adapter import JevSystemOneAdapter
                import os
                api_key = os.environ.get("JEV_API_KEY", "")
                api_url = os.environ.get("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
                model = os.environ.get("JEV_MODEL", "jev-latest")
                self.jev_adapter = JevSystemOneAdapter(api_key=api_key, api_url=api_url, model=model)
            except Exception:
                self.jev_adapter = None
        else:
            self.jev_adapter = jev_adapter

    def record_evidence(
        self,
        user_id: int,
        skill_id: str,
        source_type: str,
        source_id: str,
        score: float,
        question_difficulty: int = 3,
        grader_confidence: float = 0.85,
        evidence_quote: str | None = None,
        input_mode: str = "text",
        rubric_scores: dict[str, Any] | None = None,
        flags: list[str] | None = None,
    ) -> UserSkillEvidenceRecord:
        norm_sid = self.taxonomy.normalize_skill_id(skill_id)
        if not norm_sid:
            raise ValueError(f"Unknown or unmapped skill: {skill_id}")

        clamped_score = max(0.0, min(1.0, float(score)))
        clamped_conf = max(0.1, min(1.0, float(grader_confidence)))
        clamped_diff = max(1, min(5, int(question_difficulty)))

        # Check existing evidence for idempotency
        stmt = select(UserSkillEvidenceRecord).where(
            UserSkillEvidenceRecord.source_type == source_type,
            UserSkillEvidenceRecord.source_id == str(source_id),
            UserSkillEvidenceRecord.skill_id == norm_sid,
        )
        existing = self.session.scalars(stmt).first()
        if existing:
            existing.score = Decimal(str(round(clamped_score, 2)))
            existing.grader_confidence = Decimal(str(round(clamped_conf, 2)))
            existing.question_difficulty = clamped_diff
            existing.evidence_quote = evidence_quote
            existing.rubric_scores = rubric_scores or {}
            existing.flags = flags or []
            self.session.flush()
            self.session.commit()
            return existing

        record = UserSkillEvidenceRecord(
            user_id=user_id,
            skill_id=norm_sid,
            source_type=source_type,
            source_id=str(source_id),
            question_difficulty=clamped_diff,
            score=Decimal(str(round(clamped_score, 2))),
            grader_confidence=Decimal(str(round(clamped_conf, 2))),
            evidence_quote=evidence_quote,
            input_mode=input_mode,
            rubric_scores=rubric_scores or {},
            flags=flags or [],
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.flush()
        self.session.commit()
        return record

    def recalculate_user_skills(self, user_id: int) -> UserCareerProfileRecord:
        stmt = (
            select(UserSkillEvidenceRecord)
            .where(UserSkillEvidenceRecord.user_id == user_id)
            .order_by(UserSkillEvidenceRecord.created_at.asc())
        )
        evs = list(self.session.scalars(stmt).all())

        ev_by_skill: dict[str, list[EvidenceInput]] = {}
        for r in evs:
            item = EvidenceInput(
                skill_id=r.skill_id,
                score=float(r.score),
                difficulty=r.question_difficulty,
                grader_confidence=float(r.grader_confidence),
                source_type=r.source_type,
                created_at=r.created_at,
            )
            ev_by_skill.setdefault(r.skill_id, []).append(item)

        now = datetime.now(timezone.utc)
        skill_estimates: list[SkillEstimateResult] = []

        # Recalculate each skill
        for skill_id, items in ev_by_skill.items():
            est = SkillLevelEstimator.estimate_skill(skill_id, items, now=now)
            skill_estimates.append(est)

            # Upsert into UserSkillLevelRecord
            level_rec = self.session.get(UserSkillLevelRecord, (user_id, skill_id))
            if not level_rec:
                level_rec = UserSkillLevelRecord(
                    user_id=user_id,
                    skill_id=skill_id,
                )
                self.session.add(level_rec)

            level_rec.ability_score = Decimal(str(est.ability_score))
            level_rec.level = est.level
            level_rec.confidence = Decimal(str(est.confidence))
            level_rec.evidence_count = est.evidence_count
            level_rec.max_difficulty_passed = est.max_difficulty_passed
            level_rec.last_evidence_at = est.last_evidence_at
            level_rec.updated_at = now

        # Recalculate Career Profile
        career_res = SkillLevelEstimator.estimate_career_profile(skill_estimates)
        profile_rec = self.session.get(UserCareerProfileRecord, user_id)
        if not profile_rec:
            profile_rec = UserCareerProfileRecord(user_id=user_id)
            self.session.add(profile_rec)

        profile_rec.primary_role_track = career_res.primary_role_track
        profile_rec.secondary_role_track = career_res.secondary_role_track
        profile_rec.role_confidence = Decimal(str(career_res.role_confidence))
        profile_rec.overall_level = career_res.overall_level
        profile_rec.top_skills = career_res.top_skills
        profile_rec.weak_skills = career_res.weak_skills
        profile_rec.updated_at = now

        self.session.flush()
        # Bắt buộc commit: service không nằm sau repository nào commit thay,
        # nếu chỉ flush thì session đóng là rollback sạch dữ liệu tracking.
        self.session.commit()
        return profile_rec

    def get_user_skills_dict(self, user_id: int) -> dict[str, SkillEstimateResult]:
        stmt = select(UserSkillLevelRecord).where(UserSkillLevelRecord.user_id == user_id)
        recs = list(self.session.scalars(stmt).all())
        result: dict[str, SkillEstimateResult] = {}
        for r in recs:
            result[r.skill_id] = SkillEstimateResult(
                skill_id=r.skill_id,
                ability_score=float(r.ability_score),
                level=r.level,
                confidence=float(r.confidence),
                evidence_count=r.evidence_count,
                max_difficulty_passed=r.max_difficulty_passed,
                last_evidence_at=r.last_evidence_at,
            )
        return result

    def get_user_career_profile(self, user_id: int) -> UserCareerProfileRecord | None:
        rec = self.session.get(UserCareerProfileRecord, user_id)
        if not rec:
            return self.recalculate_user_skills(user_id)
        return rec

    def evaluate_job_readiness(
        self,
        user_id: int,
        job_id: str,
        force_refresh: bool = False,
    ) -> JobReadinessAssessment:
        job = self.session.get(JobPostingRecord, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if not force_refresh:
            existing = self.session.scalars(
                select(JobReadinessRecord).where(
                    JobReadinessRecord.user_id == user_id,
                    JobReadinessRecord.job_id == job_id,
                )
            ).first()
            if existing:
                # Check if still fresh (e.g. within 2 hours)
                age = (datetime.now(timezone.utc) - (existing.computed_at if existing.computed_at.tzinfo else existing.computed_at.replace(tzinfo=timezone.utc))).total_seconds()
                if age < 7200:
                    req_items = [
                        JobRequirementItem(
                            skill_id=r["skill_id"],
                            name=r.get("name", r["skill_id"]),
                            importance=r.get("importance", "must"),
                            required_level=r.get("required_level", "middle"),
                            required_level_num=r.get("required_level_num", 3),
                            user_level=r.get("user_level", "none"),
                            user_level_num=r.get("user_level_num", 0),
                            status=r.get("status", "unknown"),
                            confidence=r.get("confidence", 0.0),
                            level_assumed=r.get("level_assumed", False),
                        )
                        for r in (existing.requirements_breakdown or [])
                    ]
                    return JobReadinessAssessment(
                        job_id=job_id,
                        match_percent=existing.match_percent,
                        verdict=existing.verdict,
                        data_coverage=float(existing.data_coverage),
                        requirements=req_items,
                        explanation=existing.explanation or "",
                        recommended_skills=existing.recommended_skills or [],
                    )

        user_skills = self.get_user_skills_dict(user_id)
        assessment = JobReadinessEvaluator.evaluate(
            job_id=job.job_id,
            job_title=job.title,
            job_seniority=job.seniority,
            skills_required=job.skills_required or [],
            technologies=job.technologies or [],
            cleaned_jd_text=job.cleaned_jd_text or "",
            user_skills=user_skills,
        )

        if self.jev_adapter and self.jev_adapter.is_available():
            req_dicts = [{"skill_id": r.skill_id, "importance": r.importance, "required_level": r.required_level} for r in assessment.requirements]
            skills_summary = {sid: {"level": s.level, "ability_score": s.ability_score, "confidence": s.confidence} for sid, s in user_skills.items()}
            jev_res = self.jev_adapter.evaluate_readiness(
                job_title=job.title,
                job_seniority=job.seniority,
                requirements=req_dicts,
                candidate_skills=skills_summary,
                cleaned_jd_text=job.cleaned_jd_text or "",
            )
            if jev_res and "match_percent" in jev_res:
                assessment = JobReadinessAssessment(
                    job_id=assessment.job_id,
                    match_percent=int(jev_res.get("match_percent", assessment.match_percent)),
                    verdict=str(jev_res.get("verdict", assessment.verdict)),
                    data_coverage=assessment.data_coverage,
                    requirements=assessment.requirements,
                    explanation=str(jev_res.get("explanation", assessment.explanation)),
                    recommended_skills=list(jev_res.get("recommended_skills", assessment.recommended_skills)),
                )

        # Cache in DB
        check_rec = self.session.scalars(
            select(JobReadinessRecord).where(
                JobReadinessRecord.user_id == user_id,
                JobReadinessRecord.job_id == job_id,
            )
        ).first()

        req_dicts = [
            {
                "skill_id": it.skill_id,
                "name": it.name,
                "importance": it.importance,
                "required_level": it.required_level,
                "required_level_num": it.required_level_num,
                "user_level": it.user_level,
                "user_level_num": it.user_level_num,
                "status": it.status,
                "confidence": it.confidence,
                "level_assumed": it.level_assumed,
            }
            for it in assessment.requirements
        ]

        if not check_rec:
            check_rec = JobReadinessRecord(
                user_id=user_id,
                job_id=job_id,
                match_percent=assessment.match_percent,
                verdict=assessment.verdict,
                data_coverage=Decimal(str(assessment.data_coverage)),
                requirements_breakdown=req_dicts,
                explanation=assessment.explanation,
                recommended_skills=assessment.recommended_skills,
                computed_at=datetime.now(timezone.utc),
            )
            self.session.add(check_rec)
        else:
            check_rec.match_percent = assessment.match_percent
            check_rec.verdict = assessment.verdict
            check_rec.data_coverage = Decimal(str(assessment.data_coverage))
            check_rec.requirements_breakdown = req_dicts
            check_rec.explanation = assessment.explanation
            check_rec.recommended_skills = assessment.recommended_skills
            check_rec.computed_at = datetime.now(timezone.utc)

        self.session.flush()
        self.session.commit()
        return assessment

    def sync_from_interview_session(self, session_id: int) -> int:
        """Ghi bằng chứng từ các lượt phỏng vấn đã được server chấm điểm.

        Mô hình dữ liệu hiện tại: câu hỏi và câu trả lời thường nằm CÙNG một
        bản ghi turn (speaker='ai', câu trả lời ở transcribed_text), nên không
        được lọc theo speaker=candidate. Một lượt chỉ được ghi khi có đủ:
        - câu trả lời thật (transcribed_text không rỗng),
        - bản chấm điểm do server tạo (AnswerEvaluation.overall_score, thang 0-10),
        - turn gắn đúng question_id trong ngân hàng câu hỏi.
        Không đoán câu hỏi theo selection_order (thứ tự bắt đầu lại ở mỗi stage).
        """
        session_rec = self.session.get(InterviewSession, session_id)
        if not session_rec or not session_rec.candidate_id:
            return 0

        user_id = session_rec.candidate_id
        recorded = 0

        for turn in session_rec.turns:
            recorded += self._record_turn_evidence(user_id, session_id, turn)

        if recorded > 0:
            self.recalculate_user_skills(user_id)
        return recorded

    def sync_interview_turn(self, session_id: int, turn_number: int) -> int:
        """Ghi bằng chứng cho MỘT lượt đã được server chấm điểm.

        Dùng cho luồng voice/JD realtime: mỗi câu trả lời được đánh giá và
        đồng bộ ngay, không cần chờ kết thúc buổi phỏng vấn.
        """
        session_rec = self.session.get(InterviewSession, session_id)
        if not session_rec or not session_rec.candidate_id:
            return 0
        turn = next(
            (t for t in session_rec.turns if int(t.turn_number) == int(turn_number)),
            None,
        )
        if turn is None:
            return 0
        recorded = self._record_turn_evidence(
            session_rec.candidate_id, session_id, turn,
        )
        if recorded > 0:
            self.recalculate_user_skills(session_rec.candidate_id)
        return recorded

    def _record_turn_evidence(self, user_id: int, session_id: int, turn: Any) -> int:
        answer_text = (turn.transcribed_text or "").strip()
        if not answer_text:
            return 0

        eval_rec = getattr(turn, "evaluation", None)
        if not eval_rec or eval_rec.overall_score is None:
            return 0

        if not turn.question_id:
            # Không xác định được câu hỏi -> bỏ qua thay vì gán kỹ năng sai.
            return 0

        qb = self.session.get(QuestionBank, turn.question_id)
        if not qb or not qb.skill_ids:
            return 0

        raw_score = float(eval_rec.overall_score)  # constraint DB: 0..10
        norm_score = max(0.0, min(1.0, raw_score / 10.0))
        diff = qb.difficulty or 3

        recorded = 0
        for sid in set(qb.skill_ids):
            norm_sid = self.taxonomy.normalize_skill_id(sid)
            if not norm_sid:
                continue
            self.record_evidence(
                user_id=user_id,
                skill_id=norm_sid,
                source_type="interview_session",
                source_id=f"session_{session_id}_turn_{turn.turn_id}",
                score=norm_score,
                question_difficulty=diff,
                grader_confidence=0.90,
                evidence_quote=answer_text[:300],
                input_mode="voice" if turn.audio_url else "text",
            )
            recorded += 1
        return recorded

    @staticmethod
    def _practice_history_items(record: PracticeHistoryRecord) -> list[Any]:
        if not record.questions_summary:
            return []
        import json
        try:
            items = json.loads(record.questions_summary)
        except Exception:
            return []
        return items if isinstance(items, list) else []

    def _load_verified_practice_evaluations(
        self, user_id: int, question_id: int, evaluation_ids: Any,
    ) -> list[Any]:
        """Chỉ lấy đánh giá do server lưu, đúng user và đúng câu hỏi."""
        rows = fetch_practice_evaluations_by_ids(self.session, evaluation_ids)
        return [
            r for r in rows
            if int(r.user_id) == int(user_id) and int(r.question_id) == int(question_id)
        ]

    @staticmethod
    def _compose_verified_practice_evidence(rows: list[Any]) -> tuple[float, str, float, str] | None:
        """Tính điểm bằng chứng từ các thành phần server đã chấm.

        Điểm = tổng điểm thành phần / tổng thang điểm thành phần. Không dùng
        score client gửi. Không có câu trả lời thật -> trả None (không ghi).
        """
        total_max = sum(float(r.part_max) for r in rows)
        if total_max <= 0:
            return None
        total_score = sum(float(r.part_score) for r in rows)
        norm_score = max(0.0, min(1.0, total_score / total_max))

        quotes = [(r.answer_text or "").strip() for r in rows]
        quote = max(quotes, key=len)
        if not quote:
            return None

        confidence = min(0.90, 0.70 + 0.10 * len(rows))
        parts = {r.part for r in rows}
        if parts == {PART_VOICE}:
            input_mode = "voice"
        elif len(parts) > 1:
            input_mode = "mixed"
        else:
            input_mode = "text"
        return norm_score, quote[:300], confidence, input_mode

    def _sync_practice_history_items(self, user_id: int, history_id: Any, items: list[Any]) -> int:
        recorded = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                qid_int = int(item.get("question_id"))
            except (TypeError, ValueError):
                continue

            q_rec = self.session.get(QuestionBank, qid_int)
            if not q_rec or not q_rec.skill_ids:
                continue

            rows = self._load_verified_practice_evaluations(
                user_id, qid_int, item.get("evaluation_ids"),
            )
            composed = self._compose_verified_practice_evidence(rows) if rows else None
            if composed is None:
                # Không có đánh giá do server lưu cho câu trả lời này -> bỏ qua.
                continue

            norm_score, quote, confidence, input_mode = composed
            diff = q_rec.difficulty or 3
            for sid in q_rec.skill_ids:
                norm_sid = self.taxonomy.normalize_skill_id(sid)
                if not norm_sid:
                    continue
                self.record_evidence(
                    user_id=user_id,
                    skill_id=norm_sid,
                    source_type="practice_history",
                    source_id=f"hist_{history_id}_q_{qid_int}",
                    score=norm_score,
                    question_difficulty=diff,
                    grader_confidence=confidence,
                    evidence_quote=quote,
                    input_mode=input_mode,
                )
                recorded += 1
        return recorded

    def sync_from_practice_history(self, user_id: int) -> int:
        stmt = select(PracticeHistoryRecord).where(PracticeHistoryRecord.user_id == user_id)
        recorded = 0
        for h in self.session.scalars(stmt).all():
            items = self._practice_history_items(h)
            if items:
                recorded += self._sync_practice_history_items(user_id, h.history_id, items)
        if recorded > 0:
            self.recalculate_user_skills(user_id)
        return recorded

    def sync_from_practice_history_record(self, record: PracticeHistoryRecord) -> int:
        if not record.user_id:
            return 0
        items = self._practice_history_items(record)
        if not items:
            return 0
        recorded = self._sync_practice_history_items(record.user_id, record.history_id, items)
        if recorded > 0:
            self.recalculate_user_skills(record.user_id)
        return recorded

    def get_skill_evidence(self, user_id: int, skill_id: str) -> list[UserSkillEvidenceRecord]:
        norm_sid = self.taxonomy.normalize_skill_id(skill_id) or skill_id
        stmt = (
            select(UserSkillEvidenceRecord)
            .where(
                UserSkillEvidenceRecord.user_id == user_id,
                UserSkillEvidenceRecord.skill_id == norm_sid,
            )
            .order_by(UserSkillEvidenceRecord.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())
