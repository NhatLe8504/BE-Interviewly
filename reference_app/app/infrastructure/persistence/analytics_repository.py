from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import re
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from ...domain.analytics import (
    CandidateDashboard,
    CandidateKpiStats,
    HistorySessionItem,
    ProgressTrendPoint,
    ProgressTrends,
    RecentSessionSummary,
    SessionDetail,
    SessionResultReport,
    SkillRadarScore,
    TurnDetailItem,
    WeakPointRecommendation,
)
from .models.enums import SessionStatus
from .models.session_plan import InterviewFlowState
from .models.session import (
    AnswerEvaluation,
    InterviewSession,
    InterviewTurn,
    SpeechQualityAnalysis,
)
from .score_rollup import answer_groups


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (Decimal, int, float)):
        return float(val)
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return default


def _normalize_score_100(val: Any, default: float = 0.0) -> float:
    raw = _to_float(val, default)
    if 0.0 < raw <= 10.0:
        return round(raw * 10.0, 1)
    return round(raw, 1)


def _star_from_feedback(feedback: str | None) -> dict[str, bool] | None:
    match = re.match(r"<!--STAR:(\{[^\n]*\})-->\n?", feedback or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except (ValueError, TypeError):
        return None
    keys = ("situation", "task", "action", "result")
    return {key: parsed[key] for key in keys} if isinstance(parsed, dict) and all(
        type(parsed.get(key)) is bool for key in keys
    ) else None


class SqlAlchemyAnalyticsRepository:
    def get_dashboard(self, session: Session, candidate_id: int) -> CandidateDashboard:
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.candidate_id == candidate_id)
            .options(
                selectinload(InterviewSession.domain),
                selectinload(InterviewSession.role),
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.evaluation),
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.speech_analysis),
            )
            .order_by(desc(InterviewSession.started_at))
        )
        all_sessions = list(session.scalars(stmt).all())
        total_interviews = len(all_sessions)

        completed_sessions = [
            s for s in all_sessions if s.status == SessionStatus.completed
        ]
        completed_count = len(completed_sessions)

        scores = [
            _normalize_score_100(s.total_score)
            for s in completed_sessions
            if s.total_score is not None
        ]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None

        total_practice_minutes = 0
        for s in all_sessions:
            if s.completed_at and s.started_at and s.completed_at > s.started_at:
                diff = int((s.completed_at - s.started_at).total_seconds() / 60)
                total_practice_minutes += max(diff, 1)

        # Calculate streak
        streak_days = 0
        if all_sessions:
            dates = sorted(
                {s.started_at.date() for s in all_sessions if s.started_at},
                reverse=True,
            )
            now_date = datetime.now(timezone.utc).date()
            if dates and (dates[0] == now_date or (now_date - dates[0]).days <= 1):
                cur = dates[0]
                streak_days = 1
                for nxt in dates[1:]:
                    if (cur - nxt).days == 1:
                        streak_days += 1
                        cur = nxt
                    else:
                        break

        kpi = CandidateKpiStats(
            total_interviews=total_interviews,
            completed_interviews=completed_count,
            avg_score=avg_score,
            total_practice_minutes=total_practice_minutes,
            streak_days=streak_days,
        )

        clarity_scores: list[float] = []
        logic_scores: list[float] = []
        example_scores: list[float] = []
        star_scores: list[float] = []

        for s in completed_sessions:
            if s.total_score is None:
                continue
            for t in s.turns:
                if t.evaluation:
                    if t.evaluation.clarity_score is not None:
                        clarity_scores.append(_normalize_score_100(t.evaluation.clarity_score))
                    if t.evaluation.logic_score is not None:
                        logic_scores.append(_normalize_score_100(t.evaluation.logic_score))
                    if t.evaluation.example_score is not None:
                        example_scores.append(_normalize_score_100(t.evaluation.example_score))
                    star = _star_from_feedback(t.evaluation.feedback_text) if t.evaluation.question_type == "behavioral" else None
                    if star is not None:
                        star_scores.append(25.0 * sum(star.values()))

        clarity = round(sum(clarity_scores) / len(clarity_scores), 1) if clarity_scores else None
        logic = round(sum(logic_scores) / len(logic_scores), 1) if logic_scores else None
        evidence = round(sum(example_scores) / len(example_scores), 1) if example_scores else None
        star_method = round(sum(star_scores) / len(star_scores), 1) if star_scores else None

        skill_radar = SkillRadarScore(
            clarity=clarity,
            logic=logic,
            evidence=evidence,
            delivery=None,
            star_method=star_method,
        )

        # Recent sessions
        recent_sessions: list[RecentSessionSummary] = []
        for s in all_sessions[:5]:
            d_name = s.domain.domain_name if s.domain else "Tổng hợp"
            r_name = s.role.role_name if s.role else "Chung"
            m_val = s.mode.value if hasattr(s.mode, "value") else str(s.mode)
            st_val = s.status.value if hasattr(s.status, "value") else str(s.status)
            sc = _normalize_score_100(s.total_score) if s.status == SessionStatus.completed and s.total_score is not None else None
            recent_sessions.append(
                RecentSessionSummary(
                    session_id=s.session_id,
                    domain_name=d_name,
                    role_name=r_name,
                    mode=m_val,
                    score=sc,
                    status=st_val,
                    started_at=s.started_at,
                )
            )

        # Recommendations based on weakest skill
        skills = [
            ("clarity", clarity, "Độ rõ ràng & Mạch lạc (Clarity)", "Tóm tắt ý chính trong 1-2 câu đầu trước khi đi sâu vào chi tiết kỹ thuật.", "Hãy giải thích ngắn gọn nguyên lý hoạt động của microservices cho một người không chuyên."),
            ("logic", logic, "Cấu trúc logic (Logical Structure)", "Nêu lý do lựa chọn, đánh đổi và cách kiểm chứng giải pháp.", "Hãy mô tả một sự cố nghiêm trọng xảy ra trên production và các bước bạn xử lý từ đầu đến cuối."),
            ("evidence", evidence, "Dẫn chứng thực tế (Concrete Examples)", "Bổ sung ví dụ hoặc cách kiểm chứng cụ thể; chỉ nêu số liệu khi bạn thực sự có.", "Hãy kể về một bài toán kỹ thuật bạn đã xử lý và cách bạn kiểm chứng kết quả."),
        ]
        sorted_skills = sorted((skill for skill in skills if skill[1] is not None), key=lambda skill: skill[1])
        recommendations = [
            WeakPointRecommendation(
                weak_area=sk[2],
                score=sk[1],
                recommendation=sk[3],
                suggested_question=sk[4],
            )
            for sk in sorted_skills[:2]
        ]

        return CandidateDashboard(
            candidate_id=candidate_id,
            kpi=kpi,
            skill_radar=skill_radar,
            recent_sessions=recent_sessions,
            recommendations=recommendations,
        )

    def get_progress_trends(
        self, session: Session, candidate_id: int, limit: int = 10
    ) -> ProgressTrends:
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.candidate_id == candidate_id)
            .options(
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.evaluation),
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.speech_analysis),
            )
            .order_by(desc(InterviewSession.started_at))
            .limit(limit)
        )
        sessions = list(session.scalars(stmt).all())
        sessions.reverse()

        trends: list[ProgressTrendPoint] = []
        all_wpms: list[float] = []
        all_fillers: list[int] = []
        all_star_rates: list[float] = []

        for s in sessions:
            date_str = s.started_at.strftime("%d/%m") if s.started_at else "N/A"
            overall = _normalize_score_100(s.total_score) if s.status == SessionStatus.completed and s.total_score is not None else None

            c_scores: list[float] = []
            l_scores: list[float] = []
            e_scores: list[float] = []
            s_wpms: list[float] = []
            s_fillers = 0
            has_filler_analysis = False
            star_rates: list[float] = []

            for t in s.turns:
                if overall is not None and t.evaluation:
                    if t.evaluation.clarity_score is not None:
                        c_scores.append(_normalize_score_100(t.evaluation.clarity_score))
                    if t.evaluation.logic_score is not None:
                        l_scores.append(_normalize_score_100(t.evaluation.logic_score))
                    if t.evaluation.example_score is not None:
                        e_scores.append(_normalize_score_100(t.evaluation.example_score))
                    star = _star_from_feedback(t.evaluation.feedback_text) if t.evaluation.question_type == "behavioral" else None
                    if star is not None:
                        star_rates.append(25.0 * sum(star.values()))
                        all_star_rates.append(25.0 * sum(star.values()))
                if t.speech_analysis:
                    if t.speech_analysis.speaking_pace is not None:
                        val = _to_float(t.speech_analysis.speaking_pace)
                        s_wpms.append(val)
                        all_wpms.append(val)
                    if t.speech_analysis.filler_word_count is not None:
                        has_filler_analysis = True
                        s_fillers += t.speech_analysis.filler_word_count
                        all_fillers.append(t.speech_analysis.filler_word_count)

            clarity = round(sum(c_scores) / len(c_scores), 1) if c_scores else None
            logic = round(sum(l_scores) / len(l_scores), 1) if l_scores else None
            example = round(sum(e_scores) / len(e_scores), 1) if e_scores else None
            wpm = round(sum(s_wpms) / len(s_wpms), 1) if s_wpms else None
            star_rate = round(sum(star_rates) / len(star_rates), 1) if star_rates else None

            trends.append(
                ProgressTrendPoint(
                    session_id=s.session_id,
                    date=date_str,
                    overall_score=overall,
                    clarity_score=clarity,
                    logic_score=logic,
                    example_score=example,
                    speaking_pace_wpm=wpm,
                    filler_words_count=s_fillers if has_filler_analysis else None,
                    star_completion_rate=star_rate,
                )
            )

        avg_wpm = round(sum(all_wpms) / len(all_wpms), 1) if all_wpms else None
        avg_filler = round(sum(all_fillers) / len(all_fillers), 1) if all_fillers else None
        star_mastery = round(sum(all_star_rates) / len(all_star_rates), 1) if all_star_rates else None

        return ProgressTrends(
            candidate_id=candidate_id,
            trends=trends,
            avg_wpm=avg_wpm,
            avg_filler_count=avg_filler,
            star_mastery_rate=star_mastery,
        )

    def get_history(
        self,
        session: Session,
        candidate_id: int,
        page: int = 1,
        page_size: int = 10,
        domain_id: int | None = None,
        role_id: int | None = None,
        mode: str | None = None,
        status: str | None = None,
    ) -> tuple[list[HistorySessionItem], int]:
        filters = [InterviewSession.candidate_id == candidate_id]

        if domain_id is not None:
            filters.append(InterviewSession.domain_id == domain_id)
        if role_id is not None:
            filters.append(InterviewSession.role_id == role_id)
        if mode:
            filters.append(InterviewSession.mode == mode)
        if status:
            filters.append(InterviewSession.status == status)

        count_stmt = select(func.count(InterviewSession.session_id)).where(*filters)
        total = session.scalar(count_stmt) or 0

        stmt = (
            select(InterviewSession)
            .where(*filters)
            .options(
                selectinload(InterviewSession.domain),
                selectinload(InterviewSession.role),
                selectinload(InterviewSession.turns),
            )
            .order_by(desc(InterviewSession.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        sessions = list(session.scalars(stmt).all())

        items = [
            HistorySessionItem(
                session_id=s.session_id,
                candidate_id=s.candidate_id,
                domain_id=s.domain_id,
                domain_name=s.domain.domain_name if s.domain else None,
                role_id=s.role_id,
                role_name=s.role.role_name if s.role else None,
                experience_level=s.experience_level.value if hasattr(s.experience_level, "value") else (str(s.experience_level) if s.experience_level else None),
                language=s.language.value if hasattr(s.language, "value") else str(s.language),
                mode=s.mode.value if hasattr(s.mode, "value") else str(s.mode),
                status=s.status.value if hasattr(s.status, "value") else str(s.status),
                total_score=_normalize_score_100(s.total_score) if s.status == SessionStatus.completed and s.total_score is not None else None,
                started_at=s.started_at,
                completed_at=s.completed_at,
                total_turns=len(s.turns) if s.turns else 0,
            )
            for s in sessions
        ]
        return items, total

    def get_session_detail(
        self, session: Session, candidate_id: int, session_id: int
    ) -> SessionDetail | None:
        stmt = (
            select(InterviewSession)
            .where(
                InterviewSession.session_id == session_id,
                InterviewSession.candidate_id == candidate_id,
            )
            .options(
                selectinload(InterviewSession.domain),
                selectinload(InterviewSession.role),
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.evaluation),
                selectinload(InterviewSession.turns)
                .selectinload(InterviewTurn.speech_analysis),
            )
        )
        s = session.scalar(stmt)
        if s is None:
            return None

        sorted_turns = sorted(s.turns, key=lambda t: t.turn_number)
        turns: list[TurnDetailItem] = []
        c_scores: list[float] = []
        l_scores: list[float] = []
        e_scores: list[float] = []

        for t in sorted_turns:
            cl = _normalize_score_100(t.evaluation.clarity_score) if t.evaluation and t.evaluation.clarity_score is not None else None
            lg = _normalize_score_100(t.evaluation.logic_score) if t.evaluation and t.evaluation.logic_score is not None else None
            ex = _normalize_score_100(t.evaluation.example_score) if t.evaluation and t.evaluation.example_score is not None else None
            ov = _normalize_score_100(t.evaluation.overall_score) if t.evaluation and t.evaluation.overall_score is not None else None
            fb = t.evaluation.feedback_text if t.evaluation else None
            star = _star_from_feedback(fb)
            ideal = None
            if fb:
                match = re.match(r"<!--STAR:(\{[^\n]*\})-->\n?", fb)
                if match:
                    fb = fb[match.end():]
                fb, separator, ideal = fb.partition("\n\n[Gợi ý trả lời mẫu]: ")
                ideal = ideal.strip() if separator else None

            if cl is not None:
                c_scores.append(cl)
            if lg is not None:
                l_scores.append(lg)
            if ex is not None:
                e_scores.append(ex)

            sp = _to_float(t.speech_analysis.speaking_pace) if t.speech_analysis and t.speech_analysis.speaking_pace is not None else None
            hc = t.speech_analysis.hesitation_count if t.speech_analysis and t.speech_analysis.hesitation_count is not None else 0
            fw = t.speech_analysis.filler_word_count if t.speech_analysis and t.speech_analysis.filler_word_count is not None else 0
            tip = t.speech_analysis.tips_text if t.speech_analysis else None

            turns.append(
                TurnDetailItem(
                    turn_id=t.turn_id,
                    turn_number=t.turn_number,
                    speaker=t.speaker.value if hasattr(t.speaker, "value") else str(t.speaker),
                    question_id=t.question_id,
                    message_text=t.message_text,
                    audio_url=t.audio_url,
                    user_audio_url=t.user_audio_url,
                    transcribed_text=t.transcribed_text,
                    clarity_score=cl,
                    logic_score=lg,
                    example_score=ex,
                    overall_score=ov,
                    feedback_text=fb,
                    ideal_answer=ideal,
                    question_type=t.evaluation.question_type if t.evaluation else None,
                    star_analysis=star,
                    speaking_pace=sp,
                    hesitation_count=hc,
                    filler_word_count=fw,
                    tips_text=tip,
                    created_at=t.created_at,
                )
            )

        avg_cl = round(sum(c_scores) / len(c_scores), 1) if c_scores else None
        avg_lg = round(sum(l_scores) / len(l_scores), 1) if l_scores else None
        avg_ex = round(sum(e_scores) / len(e_scores), 1) if e_scores else None

        return SessionDetail(
            session_id=s.session_id,
            candidate_id=s.candidate_id,
            domain_name=s.domain.domain_name if s.domain else None,
            role_name=s.role.role_name if s.role else None,
            experience_level=s.experience_level.value if hasattr(s.experience_level, "value") else (str(s.experience_level) if s.experience_level else None),
            language=s.language.value if hasattr(s.language, "value") else str(s.language),
            mode=s.mode.value if hasattr(s.mode, "value") else str(s.mode),
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            total_score=_normalize_score_100(s.total_score) if s.status == SessionStatus.completed and s.total_score is not None else None,
            started_at=s.started_at,
            completed_at=s.completed_at,
            turns=turns,
            avg_clarity=avg_cl,
            avg_logic=avg_lg,
            avg_example=avg_ex,
        )

    def get_session_result(
        self, session: Session, candidate_id: int, session_id: int
    ) -> SessionResultReport | None:
        detail = self.get_session_detail(session, candidate_id, session_id)
        if detail is None:
            return None

        flow = session.get(InterviewFlowState, session_id)
        groups = answer_groups(detail.turns, flow.snapshot if flow else None)
        eligible = [turn for group in groups for turn in group]
        evaluated = [turn for turn in eligible if all(score is not None for score in (
            turn.overall_score, turn.clarity_score, turn.logic_score, turn.example_score,
        ))]
        is_ready = detail.status == "completed" and bool(eligible) and len(evaluated) == len(eligible)
        evaluation_status = (
            "ready" if is_ready else
            "pending" if detail.status != "completed" else
            "partial" if eligible else "unavailable"
        )

        def average(attribute: str) -> float | None:
            if not is_ready:
                return None
            group_means = [sum(getattr(turn, attribute) for turn in group) / len(group) for group in groups]
            return round(sum(group_means) / len(group_means), 1)

        total = average("overall_score")

        if total is None:
            badge = "Chưa đủ dữ liệu để xếp loại"
        elif total >= 85.0:
            badge = "Kết quả luyện tập nổi bật"
        elif total >= 70.0:
            badge = "Kết quả luyện tập khá"
        elif total >= 50.0:
            badge = "Cần cải thiện thêm"
        else:
            badge = "Cần luyện tập nền tảng"

        clarity = average("clarity_score")
        structure = average("logic_score")
        evidence = average("example_score")

        answered = [turn for turn in detail.turns if turn.transcribed_text or
                    (turn.speaker == "candidate" and turn.message_text)]
        wpms = [turn.speaking_pace for turn in answered if turn.speaking_pace is not None]
        avg_wpm = round(sum(wpms) / len(wpms), 1) if wpms else None

        if avg_wpm is None:
            pace_rating = None
        elif avg_wpm < 110.0:
            pace_rating = "Quá chậm (Too Slow)"
        elif avg_wpm <= 160.0:
            pace_rating = "Lý tưởng (Ideal)"
        else:
            pace_rating = "Quá nhanh (Too Fast)"

        analyzed_turn_ids = set(session.scalars(
            select(SpeechQualityAnalysis.turn_id).join(InterviewTurn)
            .where(InterviewTurn.session_id == session_id)
        ))
        analyzed_answers = [turn for turn in answered if turn.turn_id in analyzed_turn_ids]
        total_fillers = sum(turn.filler_word_count for turn in analyzed_answers) if analyzed_answers else None
        star_analysis = next((turn.star_analysis for turn in reversed(evaluated)
                              if turn.star_analysis is not None and turn.question_type == "behavioral"), None)

        return SessionResultReport(
            session_id=detail.session_id,
            candidate_id=detail.candidate_id,
            status=detail.status,
            total_score=total,
            readiness_badge=badge,
            clarity_score=clarity,
            structure_score=structure,
            evidence_score=evidence,
            speaking_pace_wpm=avg_wpm,
            pace_rating=pace_rating,
            filler_count=total_fillers,
            filler_words=[],
            pause_duration=None,
            star_analysis=star_analysis,
            evaluation_status=evaluation_status,
            evaluated_turns=len(evaluated),
            eligible_turns=len(eligible),
            turns=detail.turns,
            total_turns=len(detail.turns),
            performance_rating=badge,
        )
