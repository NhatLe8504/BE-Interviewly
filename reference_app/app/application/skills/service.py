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
from .estimator import EvidenceInput, SkillEstimateResult, SkillLevelEstimator
from .readiness import JobReadinessAssessment, JobReadinessEvaluator
from .taxonomy import get_default_taxonomy

logger = logging.getLogger(__name__)


class UserSkillService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.taxonomy = get_default_taxonomy()

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
        return assessment

    def sync_from_interview_session(self, session_id: int) -> int:
        session_rec = self.session.get(InterviewSession, session_id)
        if not session_rec or not session_rec.candidate_id:
            return 0

        user_id = session_rec.candidate_id
        recorded = 0

        # Iterate candidate turns
        for turn in session_rec.turns:
            if str(getattr(turn, "speaker", "")).lower() not in ("candidate", "turnspeaker.candidate"):
                continue

            eval_rec = getattr(turn, "evaluation", None)
            if not eval_rec:
                continue

            # Normalized score from overall_score (which is 0-10)
            raw_score = float(eval_rec.overall_score) if eval_rec.overall_score is not None else 5.0
            norm_score = max(0.0, min(1.0, raw_score / 10.0))

            # Determine skills for this turn
            extracted_skills: list[str] = []
            if turn.question_id:
                qb = self.session.get(QuestionBank, turn.question_id)
                if qb:
                    if getattr(qb, "skill_ids", None):
                        extracted_skills.extend(qb.skill_ids)
                    if not extracted_skills and qb.question_text:
                        for s in self.taxonomy.extract_skills_from_text(qb.question_text):
                            extracted_skills.append(s.id)

            if not extracted_skills and turn.message_text:
                for s in self.taxonomy.extract_skills_from_text(turn.message_text):
                    extracted_skills.append(s.id)

            # If still none, check domain
            if not extracted_skills and session_rec.domain:
                d_skills = self.taxonomy.get_skills_for_role(session_rec.domain.domain_name.lower())
                if d_skills:
                    extracted_skills.append(d_skills[0].id)

            for sid in set(extracted_skills):
                self.record_evidence(
                    user_id=user_id,
                    skill_id=sid,
                    source_type="interview_turn",
                    source_id=f"turn_{turn.turn_id}",
                    score=norm_score,
                    question_difficulty=3,
                    grader_confidence=0.85,
                    evidence_quote=(turn.transcribed_text or turn.message_text or "")[:300],
                    input_mode="voice" if turn.transcribed_text else "text",
                )
                recorded += 1

        if recorded > 0:
            self.recalculate_user_skills(user_id)
        return recorded
