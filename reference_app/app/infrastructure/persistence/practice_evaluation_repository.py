from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select

from .models.user_skills import PracticeEvaluationRecord

logger = logging.getLogger(__name__)

PART_CONTENT = "content"
PART_VOICE = "voice"


def save_practice_evaluation(
    session: Any,
    *,
    user_id: int,
    question_id: int,
    part: str,
    part_score: float,
    part_max: float,
    answer_text: str | None,
    method: str = "llm",
) -> PracticeEvaluationRecord:
    """Lưu một thành phần đánh giá do server tạo cho câu trả lời luyện tập.

    Chỉ gọi hàm này từ nơi server thực sự chấm điểm (LLM evaluator). Không gọi
    với điểm do client cung cấp.
    """
    record = PracticeEvaluationRecord(
        user_id=user_id,
        question_id=question_id,
        part=part,
        part_score=Decimal(str(round(float(part_score), 2))),
        part_max=Decimal(str(round(float(part_max), 2))),
        answer_text=(answer_text or None),
        method=method,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def persist_llm_evaluation(
    container: Any,
    *,
    user_id: int | None,
    question_id: int | None,
    part: str,
    part_score: float,
    part_max: float,
    answer_text: str | None,
    method: str = "llm",
) -> int | None:
    """Lưu đánh giá từ background worker (queue) bằng session riêng.

    Worker chạy sau khi request đã đóng session, nên phải tự mở session và
    commit. Trả về evaluation_id để client gửi lại khi lưu practice history.
    """
    if not user_id or not question_id:
        return None
    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return None
    session = session_factory()
    try:
        record = save_practice_evaluation(
            session,
            user_id=int(user_id),
            question_id=int(question_id),
            part=part,
            part_score=part_score,
            part_max=part_max,
            answer_text=answer_text,
            method=method,
        )
        return int(record.id)
    except Exception:
        session.rollback()
        logger.exception("Failed to persist practice evaluation for user %s question %s", user_id, question_id)
        return None
    finally:
        session.close()


def fetch_practice_evaluations_by_ids(session: Any, evaluation_ids: Iterable[Any]) -> list[PracticeEvaluationRecord]:
    ids: list[int] = []
    for raw in evaluation_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    stmt = select(PracticeEvaluationRecord).where(PracticeEvaluationRecord.id.in_(ids))
    return list(session.scalars(stmt).all())
