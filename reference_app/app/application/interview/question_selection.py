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

            intent_text = q.intent or q.question_text
            contexts.append(
                QuestionIntentContext(
                    question_id=q.question_id,
                    intent=intent_text,
                    stage_key=stage_key,
                    difficulty=q.difficulty or 3,
                    question_type=q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type),
                    raw_question_text=q.question_text,
                    topic_label=intent_text[:60] + ("..." if len(intent_text) > 60 else ""),
                )
            )

        session.flush()
        return contexts

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

        intent_text = new_q.intent or new_q.question_text
        return QuestionIntentContext(
            question_id=new_q.question_id,
            intent=intent_text,
            stage_key=stage_key,
            difficulty=new_q.difficulty or 3,
            question_type=new_q.question_type.value if hasattr(new_q.question_type, "value") else str(new_q.question_type),
            raw_question_text=new_q.question_text,
            topic_label=intent_text[:60] + ("..." if len(intent_text) > 60 else ""),
        )
