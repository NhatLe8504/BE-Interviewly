from __future__ import annotations

import random
from typing import Any
from sqlalchemy import select, and_, not_

from ...infrastructure.persistence.models.catalog import QuestionBank
from ...infrastructure.persistence.models.enums import QuestionModerationStatus
from ...infrastructure.persistence.models.session_plan import (
    InterviewSessionConfig,
    SessionQuestionSelection,
)
from .intent_composer import QuestionIntentContext


class QuestionSelectionService:
    """
    Handles question sampling (auto_random / manual / mixed), re-rolling,
    and stage-level intent provisioning. Enforces moderation gates.
    """

    @staticmethod
    def get_approved_questions(
        session: Any,
        domain_id: int | None = None,
        role_id: int | None = None,
        stage_key: str = "technical",
        exclude_ids: list[int] | None = None,
    ) -> list[QuestionBank]:
        stmt = select(QuestionBank).where(
            QuestionBank.is_active == True,
            QuestionBank.moderation_status == QuestionModerationStatus.approved,
        )
        if domain_id is not None:
            stmt = stmt.where(QuestionBank.domain_id == domain_id)
        if role_id is not None:
            stmt = stmt.where((QuestionBank.role_id == role_id) | (QuestionBank.role_id == None))
        if exclude_ids:
            stmt = stmt.where(not_(QuestionBank.question_id.in_(exclude_ids)))

        result = session.execute(stmt).scalars().all()
        return list(result)

    @classmethod
    def sample_questions_for_stage(
        cls,
        session: Any,
        session_id: int,
        stage_key: str,
        source_mode: str = "auto_random",
        target_count: int = 1,
        selected_question_ids: list[int] | None = None,
        domain_id: int | None = None,
        role_id: int | None = None,
        exclude_used_ids: list[int] | None = None,
    ) -> list[QuestionIntentContext]:
        exclude = list(exclude_used_ids or [])
        chosen_questions: list[QuestionBank] = []

        # 1. Manual / Pre-selected mode
        if source_mode in ("manual", "mixed") and selected_question_ids:
            stmt = select(QuestionBank).where(
                QuestionBank.question_id.in_(selected_question_ids),
                QuestionBank.moderation_status == QuestionModerationStatus.approved,
                QuestionBank.is_active == True,
            )
            manual_qs = list(session.execute(stmt).scalars().all())
            for mq in manual_qs:
                if mq.question_id not in exclude:
                    chosen_questions.append(mq)
                    exclude.append(mq.question_id)
                if len(chosen_questions) >= target_count and source_mode == "manual":
                    break

        # 2. Auto-random backfill (if auto_random or mixed and still need more)
        needed = target_count - len(chosen_questions)
        if needed > 0 and source_mode in ("auto_random", "mixed"):
            pool = cls.get_approved_questions(
                session=session,
                domain_id=domain_id,
                role_id=role_id,
                stage_key=stage_key,
                exclude_ids=exclude,
            )
            if not pool and domain_id is not None:
                # Fallback to domain-agnostic pool if domain pool is small
                pool = cls.get_approved_questions(
                    session=session,
                    domain_id=None,
                    role_id=None,
                    stage_key=stage_key,
                    exclude_ids=exclude,
                )
            if pool:
                random.shuffle(pool)
                picks = pool[:needed]
                chosen_questions.extend(picks)

        # 3. Persist selections
        contexts: list[QuestionIntentContext] = []
        for order, q in enumerate(chosen_questions, start=1):
            record = SessionQuestionSelection(
                session_id=session_id,
                stage_key=stage_key,
                question_id=q.question_id,
                selection_order=order,
                was_rerolled=False,
            )
            session.add(record)
            contexts.append(cls._context_from_question(q, stage_key))

        session.flush()
        return contexts

    @staticmethod
    def _context_from_question(question: QuestionBank, stage_key: str) -> QuestionIntentContext:
        intent_text = question.intent or question.question_text
        return QuestionIntentContext(
            question_id=int(question.question_id),
            intent=intent_text,
            stage_key=stage_key,
            difficulty=question.difficulty or 3,
            question_type=question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type),
            raw_question_text=question.question_text,
            topic_label=intent_text[:60] + ("..." if len(intent_text) > 60 else ""),
        )

    @staticmethod
    def get_used_question_ids(session: Any, session_id: int) -> list[int]:
        """Các câu hỏi ngân hàng đã thực sự được hỏi (gắn vào một lượt) trong session."""
        stmt = select(SessionQuestionSelection.question_id).where(
            SessionQuestionSelection.session_id == session_id,
            SessionQuestionSelection.used_at_turn.is_not(None),
        )
        return [int(qid) for qid in session.execute(stmt).scalars().all()]

    @classmethod
    def take_planned_selection(
        cls, session: Any, session_id: int, stage_key: str,
    ) -> QuestionIntentContext | None:
        """Lấy câu hỏi chưa dùng sớm nhất trong số câu hỏi đã được lên kế hoạch cho stage.

        Dùng cho luồng text: session tạo sẵn một pool câu hỏi theo stage config,
        mỗi lượt lấy lần lượt từ pool thay vì random lại.
        """
        stmt = (
            select(SessionQuestionSelection)
            .where(
                SessionQuestionSelection.session_id == session_id,
                SessionQuestionSelection.stage_key == stage_key,
                SessionQuestionSelection.used_at_turn.is_(None),
                SessionQuestionSelection.was_rerolled == False,  # noqa: E712
            )
            .order_by(SessionQuestionSelection.selection_order.asc())
        )
        selection = session.execute(stmt).scalars().first()
        if selection is None:
            return None
        question = session.get(QuestionBank, selection.question_id)
        if (
            question is None
            or not question.is_active
            or question.moderation_status != QuestionModerationStatus.approved
        ):
            return None
        return cls._context_from_question(question, stage_key)

    @staticmethod
    def mark_selection_used(
        session: Any,
        session_id: int,
        stage_key: str,
        question_id: int,
        turn_number: int,
    ) -> bool:
        """Đánh dấu câu hỏi ngân hàng đã được hỏi ở lượt `turn_number` (idempotent)."""
        stmt = (
            select(SessionQuestionSelection)
            .where(
                SessionQuestionSelection.session_id == session_id,
                SessionQuestionSelection.stage_key == stage_key,
                SessionQuestionSelection.question_id == question_id,
                SessionQuestionSelection.used_at_turn.is_(None),
            )
            .order_by(SessionQuestionSelection.selection_order.asc())
        )
        selection = session.execute(stmt).scalars().first()
        if selection is None:
            return False
        selection.used_at_turn = int(turn_number)
        return True

    @classmethod
    def reroll_question(
        cls,
        session: Any,
        session_id: int,
        stage_key: str,
        current_question_id: int,
        domain_id: int | None = None,
        role_id: int | None = None,
    ) -> QuestionIntentContext | None:
        # Mark previous selection as rerolled
        stmt = select(SessionQuestionSelection).where(
            SessionQuestionSelection.session_id == session_id,
            SessionQuestionSelection.question_id == current_question_id,
        )
        selection = session.execute(stmt).scalars().first()
        if selection:
            selection.was_rerolled = True

        # Find a replacement approved question not currently used in this session
        used_stmt = select(SessionQuestionSelection.question_id).where(
            SessionQuestionSelection.session_id == session_id,
        )
        used_ids = list(session.execute(used_stmt).scalars().all())
        if current_question_id not in used_ids:
            used_ids.append(current_question_id)

        pool = cls.get_approved_questions(
            session=session,
            domain_id=domain_id,
            role_id=role_id,
            stage_key=stage_key,
            exclude_ids=used_ids,
        )
        if not pool:
            return None

        new_q = random.choice(pool)
        new_record = SessionQuestionSelection(
            session_id=session_id,
            stage_key=stage_key,
            question_id=new_q.question_id,
            selection_order=(selection.selection_order if selection else 1) + 10,
            was_rerolled=False,
        )
        session.add(new_record)
        session.flush()

        return cls._context_from_question(new_q, stage_key)
