"""Rà soát và gắn nhãn kỹ năng cho question_bank theo bằng chứng văn bản.

Chạy từ thư mục reference_app:
    .venv/Scripts/python.exe scripts/retag_question_skills.py --report
    .venv/Scripts/python.exe scripts/retag_question_skills.py --apply
    .venv/Scripts/python.exe scripts/retag_question_skills.py --llm-suggest 10

Mặc định chỉ đọc. --apply chỉ ghi kết quả được xác minh bằng văn bản
(hoặc kỹ năng mềm hợp lệ với câu hỏi hành vi); gợi ý LLM chỉ xuất ra file để rà.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.skills.question_tagger import audit_question, suggest_skill_ids_with_llm
from app.config import Settings
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.persistence.models.catalog import QuestionBank


def _load_questions(session: Session, question_ids: list[int] | None, include_untagged: bool) -> list[QuestionBank]:
    stmt = select(QuestionBank).where(QuestionBank.is_active.is_(True)).order_by(QuestionBank.question_id)
    if question_ids:
        stmt = stmt.where(QuestionBank.question_id.in_(question_ids))
    rows = list(session.scalars(stmt).all())
    if not include_untagged:
        rows = [row for row in rows if row.skill_ids]
    return rows


def _format_audit(audit) -> str:
    parts = [
        f"#{audit.question_id} [{audit.question_type}]",
        f"current={audit.current}",
        f"final={audit.final}",
    ]
    if audit.added:
        parts.append(f"+add={audit.added}")
    if audit.dropped:
        parts.append(f"-drop={audit.dropped}")
    if audit.unknown_dropped:
        parts.append(f"-unknown={audit.unknown_dropped}")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="read-only plan (default)")
    parser.add_argument("--apply", action="store_true", help="ghi thay đổi vào DB (mặc định chỉ đọc)")
    parser.add_argument("--question-id", type=int, action="append", default=None, help="chỉ xử lý các câu hỏi này")
    parser.add_argument("--all", action="store_true", help="bao gồm cả câu chưa có nhãn")
    parser.add_argument("--verbose", action="store_true", help="in mọi câu, kể cả không đổi")
    parser.add_argument("--llm-suggest", type=int, default=0, metavar="N", help="gợi ý bằng LLM cho N câu chưa có nhãn (chỉ ghi ra file)")
    parser.add_argument("--out", default="question_tag_suggestions.json", help="file nhận gợi ý LLM")
    args = parser.parse_args()

    settings = Settings.from_env()
    engine = create_engine_from_url(settings.database_url)

    with Session(engine) as session:
        rows = _load_questions(session, args.question_id, include_untagged=args.all or args.llm_suggest > 0)
        audits = [
            audit_question(row.question_id, row.question_text, row.question_type, row.skill_ids)
            for row in rows
        ]

        for audit in audits:
            if audit.changed or args.verbose:
                print(_format_audit(audit))

        changed = [audit for audit in audits if audit.changed]
        print(
            f"Tổng: {len(audits)} câu, {len(changed)} cần đổi, "
            f"{sum(len(a.added) for a in audits)} nhãn thêm, "
            f"{sum(len(a.dropped) + len(a.unknown_dropped) for a in audits)} nhãn sai bị loại."
        )

        if args.apply and changed:
            for row, audit in zip(rows, audits):
                if audit.changed:
                    row.skill_ids = audit.final
            session.commit()
            print(f"ĐÃ GHI vào DB: {len(changed)} câu hỏi.")
        elif args.apply:
            print("Không có thay đổi nào để ghi.")

        if args.llm_suggest > 0:
            api_key = settings.openai_api_key or ""
            if not api_key.startswith("gsk_"):
                print("Thiếu GROQ_API_KEY hợp lệ — bỏ qua gợi ý LLM.")
                return 0
            suggestions: dict[str, list[str]] = {}
            for row, audit in zip(rows, audits):
                if len(suggestions) >= args.llm_suggest:
                    break
                if audit.final:
                    continue
                try:
                    ids = suggest_skill_ids_with_llm(
                        row.question_text,
                        base_url=settings.openai_base_url,
                        api_key=api_key,
                        model=settings.openai_model,
                    )
                except Exception as exc:  # pragma: no cover - phụ thuộc mạng
                    print(f"#{row.question_id}: lỗi gọi LLM: {exc}")
                    continue
                suggestions[str(row.question_id)] = ids
                print(f"#{row.question_id}: gợi ý LLM={ids}")
            Path(args.out).write_text(json.dumps(suggestions, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Đã ghi gợi ý vào {args.out} (chưa áp dụng vào DB — cần rà lại).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
