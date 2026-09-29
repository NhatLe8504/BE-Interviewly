from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...application.catalog.ports import CatalogRepositoryPort
from ...domain.catalog import (
    JobDomain,
    JobRole,
    QuestionBankItem,
    StarGuidanceTemplate,
)
from .models.catalog import JobDomain as JobDomainModel
from .models.catalog import JobRole as JobRoleModel
from .models.catalog import QuestionBank as QuestionBankModel
from .models.catalog import StarGuidanceTemplate as StarGuidanceTemplateModel
from .models.catalog import PracticeHistoryRecord as PracticeHistoryModel
from .models.catalog import QuestionSetReview as QuestionSetReviewModel
from .models.catalog import QuestionSet as QuestionSetModel
from .models.catalog import QuestionSetItem as QuestionSetItemModel
from .models.enums import ExperienceLevel, Language, QuestionType, QuestionModerationStatus


def _enum_value(val: Any) -> str | None:
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def _to_experience_level(val: str | None) -> ExperienceLevel | None:
    if val is None:
        return None
    if val == "middle":
        return ExperienceLevel.mid
    return ExperienceLevel(val)


def _to_domain(row: JobDomainModel) -> JobDomain:
    return JobDomain(
        domain_id=row.domain_id,
        domain_name=row.domain_name,
        description=row.description,
        created_at=row.created_at,
    )


def _to_role(row: JobRoleModel) -> JobRole:
    return JobRole(
        role_id=row.role_id,
        domain_id=row.domain_id,
        role_name=row.role_name,
        description=row.description,
        created_at=row.created_at,
    )


def _to_star_template(row: StarGuidanceTemplateModel) -> StarGuidanceTemplate:
    return StarGuidanceTemplate(
        star_template_id=row.star_template_id,
        title=row.title,
        situation_guide=row.situation_guide,
        task_guide=row.task_guide,
        action_guide=row.action_guide,
        result_guide=row.result_guide,
        language=_enum_value(row.language) or "vi",
        created_at=row.created_at,
    )


def _to_question(row: QuestionBankModel) -> QuestionBankItem:
    return QuestionBankItem(
        question_id=row.question_id,
        domain_id=row.domain_id,
        role_id=row.role_id,
        experience_level=_enum_value(row.experience_level),
        language=_enum_value(row.language) or "vi",
        question_type=_enum_value(row.question_type) or "behavioral",
        question_text=row.question_text,
        star_template_id=row.star_template_id,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyCatalogRepository:
    def find_available_question_ids(
        self, session: Any, question_ids: list[int], language: str,
    ) -> set[int]:
        if not question_ids:
            return set()
        stmt = select(QuestionBankModel.question_id).where(
            QuestionBankModel.question_id.in_(question_ids),
            QuestionBankModel.is_active == True,
            QuestionBankModel.moderation_status == QuestionModerationStatus.approved,
            QuestionBankModel.language == Language(language),
        )
        return set(session.execute(stmt).scalars().all())

    def list_domains(self, session: Any) -> list[JobDomain]:
        stmt = select(JobDomainModel).where(JobDomainModel.domain_name.not_like('Software Dev %')).order_by(JobDomainModel.domain_name)
        rows = session.execute(stmt).scalars().all()
        return [_to_domain(r) for r in rows]

    def get_domain_by_id(self, session: Any, domain_id: int) -> JobDomain | None:
        row = session.get(JobDomainModel, domain_id)
        return _to_domain(row) if row else None

    def add_domain(
        self, session: Any, *, domain_name: str, description: str | None = None,
    ) -> JobDomain:
        row = JobDomainModel(domain_name=domain_name, description=description)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_domain(row)

    def update_domain(
        self,
        session: Any,
        domain_id: int,
        *,
        domain_name: str | None = None,
        description: str | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> JobDomain:
        row = session.get(JobDomainModel, domain_id)
        if row is None:
            raise ValueError(f"domain {domain_id} not found")

        if fields_set is None:
            if domain_name is not None:
                row.domain_name = domain_name
            if description is not None:
                row.description = description
        else:
            if "domain_name" in fields_set and domain_name is not None:
                row.domain_name = domain_name
            if "description" in fields_set:
                row.description = description

        session.commit()
        session.refresh(row)
        return _to_domain(row)

    def delete_domain(self, session: Any, domain_id: int) -> None:
        row = session.get(JobDomainModel, domain_id)
        if row:
            session.delete(row)
            session.commit()

    def list_roles(self, session: Any, *, domain_id: int | None = None) -> list[JobRole]:
        stmt = select(JobRoleModel)
        if domain_id is not None:
            stmt = stmt.where(JobRoleModel.domain_id == domain_id)
        stmt = stmt.order_by(JobRoleModel.role_name)
        rows = session.execute(stmt).scalars().all()
        return [_to_role(r) for r in rows]

    def get_role_by_id(self, session: Any, role_id: int) -> JobRole | None:
        row = session.get(JobRoleModel, role_id)
        return _to_role(row) if row else None

    def add_role(
        self, session: Any, *, domain_id: int, role_name: str, description: str | None = None,
    ) -> JobRole:
        row = JobRoleModel(domain_id=domain_id, role_name=role_name, description=description)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_role(row)

    def update_role(
        self,
        session: Any,
        role_id: int,
        *,
        role_name: str | None = None,
        description: str | None = None,
        domain_id: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> JobRole:
        row = session.get(JobRoleModel, role_id)
        if row is None:
            raise ValueError(f"role {role_id} not found")

        if fields_set is None:
            if role_name is not None:
                row.role_name = role_name
            if description is not None:
                row.description = description
            if domain_id is not None:
                row.domain_id = domain_id
        else:
            if "role_name" in fields_set and role_name is not None:
                row.role_name = role_name
            if "description" in fields_set:
                row.description = description
            if "domain_id" in fields_set and domain_id is not None:
                row.domain_id = domain_id

        session.commit()
        session.refresh(row)
        return _to_role(row)

    def delete_role(self, session: Any, role_id: int) -> None:
        row = session.get(JobRoleModel, role_id)
        if row:
            session.delete(row)
            session.commit()

    def list_star_templates(
        self, session: Any, *, language: str | None = None,
    ) -> list[StarGuidanceTemplate]:
        stmt = select(StarGuidanceTemplateModel)
        if language is not None:
            stmt = stmt.where(StarGuidanceTemplateModel.language == Language(language))
        stmt = stmt.order_by(StarGuidanceTemplateModel.star_template_id)
        rows = session.execute(stmt).scalars().all()
        return [_to_star_template(r) for r in rows]

    def get_star_template_by_id(
        self, session: Any, star_template_id: int,
    ) -> StarGuidanceTemplate | None:
        row = session.get(StarGuidanceTemplateModel, star_template_id)
        return _to_star_template(row) if row else None

    def add_star_template(
        self,
        session: Any,
        *,
        title: str,
        situation_guide: str | None = None,
        task_guide: str | None = None,
        action_guide: str | None = None,
        result_guide: str | None = None,
        language: str = "vi",
    ) -> StarGuidanceTemplate:
        row = StarGuidanceTemplateModel(
            title=title,
            situation_guide=situation_guide,
            task_guide=task_guide,
            action_guide=action_guide,
            result_guide=result_guide,
            language=Language(language),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_star_template(row)

    def list_questions(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        is_active: bool | None = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[QuestionBankItem]:
        stmt = select(QuestionBankModel)
        if domain_id is not None:
            stmt = stmt.where(QuestionBankModel.domain_id == domain_id)
        if role_id is not None:
            stmt = stmt.where(QuestionBankModel.role_id == role_id)
        if experience_level is not None:
            stmt = stmt.where(QuestionBankModel.experience_level == _to_experience_level(experience_level))
        if question_type is not None:
            stmt = stmt.where(QuestionBankModel.question_type == QuestionType(question_type))
        if language is not None:
            stmt = stmt.where(QuestionBankModel.language == Language(language))
        if is_active is not None:
            stmt = stmt.where(QuestionBankModel.is_active == is_active)
        stmt = stmt.where(QuestionBankModel.moderation_status == QuestionModerationStatus.approved)
        stmt = stmt.order_by(QuestionBankModel.question_id.desc()).offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_to_question(r) for r in rows]

    def count_questions(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        is_active: bool | None = True,
    ) -> int:
        stmt = select(func.count(QuestionBankModel.question_id))
        if domain_id is not None:
            stmt = stmt.where(QuestionBankModel.domain_id == domain_id)
        if role_id is not None:
            stmt = stmt.where(QuestionBankModel.role_id == role_id)
        if experience_level is not None:
            stmt = stmt.where(QuestionBankModel.experience_level == _to_experience_level(experience_level))
        if question_type is not None:
            stmt = stmt.where(QuestionBankModel.question_type == QuestionType(question_type))
        if language is not None:
            stmt = stmt.where(QuestionBankModel.language == Language(language))
        if is_active is not None:
            stmt = stmt.where(QuestionBankModel.is_active == is_active)
        stmt = stmt.where(QuestionBankModel.moderation_status == QuestionModerationStatus.approved)
        return session.execute(stmt).scalar() or 0


    def get_questions_by_ids(
        self, session: Any, question_ids: list[int],
    ) -> list[QuestionBankItem]:
        if not question_ids:
            return []
        stmt = (
            select(QuestionBankModel)
            .where(
                QuestionBankModel.question_id.in_(question_ids),
                QuestionBankModel.is_active == True,
            )
        )
        rows = session.execute(stmt).scalars().all()
        row_dict = {r.question_id: _to_question(r) for r in rows}
        return [row_dict[qid] for qid in question_ids if qid in row_dict]

    def get_question_by_id(
        self, session: Any, question_id: int,
    ) -> QuestionBankItem | None:
        row = session.get(QuestionBankModel, question_id)
        return _to_question(row) if row else None

    def add_question(
        self,
        session: Any,
        *,
        domain_id: int,
        question_text: str,
        question_type: str,
        language: str = "vi",
        role_id: int | None = None,
        experience_level: str | None = None,
        star_template_id: int | None = None,
        created_by: int | None = None,
        quiz_data: dict[str, Any] | None = None,
        sample_answer: str | None = None,
        follow_up_questions: list[str] | None = None,
        tips: list[str] | None = None,
    ) -> QuestionBankItem:
        row = QuestionBankModel(
            domain_id=domain_id,
            role_id=role_id,
            experience_level=_to_experience_level(experience_level),
            language=Language(language),
            question_type=QuestionType(question_type),
            question_text=question_text,
            star_template_id=star_template_id,
            is_active=True,
            created_by=created_by,
            quiz_data=quiz_data,
            sample_answer=sample_answer,
            follow_up_questions=follow_up_questions,
            tips=tips,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_question(row)

    def update_question(
        self,
        session: Any,
        question_id: int,
        *,
        domain_id: int | None = None,
        question_text: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        star_template_id: int | None = None,
        is_active: bool | None = None,
        quiz_data: dict[str, Any] | None = None,
        sample_answer: str | None = None,
        follow_up_questions: list[str] | None = None,
        tips: list[str] | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> QuestionBankItem:
        row = session.get(QuestionBankModel, question_id)
        if row is None:
            raise ValueError(f"question {question_id} not found")

        if fields_set is None:
            if question_text is not None:
                row.question_text = question_text
            if question_type is not None:
                row.question_type = QuestionType(question_type)
            if language is not None:
                row.language = Language(language)
            if role_id is not None:
                row.role_id = role_id
            if experience_level is not None:
                row.experience_level = _to_experience_level(experience_level)
            if star_template_id is not None:
                row.star_template_id = star_template_id
            if is_active is not None:
                row.is_active = is_active
        else:
            if "question_text" in fields_set and question_text is not None:
                row.question_text = question_text
            if "question_type" in fields_set and question_type is not None:
                row.question_type = QuestionType(question_type)
            if "language" in fields_set and language is not None:
                row.language = Language(language)
            if "role_id" in fields_set:
                row.role_id = role_id
            if "experience_level" in fields_set:
                row.experience_level = _to_experience_level(experience_level)
            if "star_template_id" in fields_set:
                row.star_template_id = star_template_id
            if "is_active" in fields_set and is_active is not None:
                row.is_active = is_active
            if "domain_id" in fields_set and domain_id is not None:
                row.domain_id = domain_id
            if "quiz_data" in fields_set:
                row.quiz_data = quiz_data
            if "sample_answer" in fields_set:
                row.sample_answer = sample_answer
            if "follow_up_questions" in fields_set:
                row.follow_up_questions = follow_up_questions
            if "tips" in fields_set:
                row.tips = tips

        session.commit()
        session.refresh(row)
        return _to_question(row)

    def delete_question(self, session: Any, question_id: int) -> None:
        row = session.get(QuestionBankModel, question_id)
        if row:
            session.delete(row)
            session.commit()


    def save_practice_history(
        self, session: Any, record: PracticeHistoryModel,
    ) -> PracticeHistoryModel:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def list_practice_history(
        self, session: Any, user_id: int | None = None, limit: int = 50,
    ) -> list[PracticeHistoryModel]:
        stmt = select(PracticeHistoryModel).order_by(PracticeHistoryModel.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(PracticeHistoryModel.user_id == user_id)
        stmt = stmt.limit(limit)
        return list(session.execute(stmt).scalars().all())

    def list_question_set_reviews(
        self, session: Any, set_id: str,
    ) -> list[QuestionSetReviewModel]:
        stmt = (
            select(QuestionSetReviewModel)
            .where(QuestionSetReviewModel.set_id == str(set_id))
            .order_by(QuestionSetReviewModel.created_at.desc())
        )
        return list(session.execute(stmt).scalars().all())

    def add_question_set_review(
        self, session: Any, review: QuestionSetReviewModel,
    ) -> QuestionSetReviewModel:
        session.add(review)
        session.commit()
        session.refresh(review)
        return review

    def get_question_set_leaderboard(
        self, session: Any, set_id: str, limit: int = 10,
    ) -> list[PracticeHistoryModel]:
        stmt = (
            select(PracticeHistoryModel)
            .where(PracticeHistoryModel.source_id == str(set_id))
            .order_by(PracticeHistoryModel.average_score.desc(), PracticeHistoryModel.duration_seconds.asc())
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())

    def list_question_sets(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        level: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[QuestionSetModel], int]:
        stmt = select(QuestionSetModel).where(QuestionSetModel.is_active == True)
        count_stmt = select(func.count(QuestionSetModel.set_id)).where(QuestionSetModel.is_active == True)
        if domain_id is not None:
            stmt = stmt.where(QuestionSetModel.domain_id == domain_id)
            count_stmt = count_stmt.where(QuestionSetModel.domain_id == domain_id)
        if level is not None and level != "all":
            stmt = stmt.where(QuestionSetModel.experience_level == level)
            count_stmt = count_stmt.where(QuestionSetModel.experience_level == level)
        if search and search.strip():
            kw = f"%{search.strip().lower()}%"
            stmt = stmt.where(QuestionSetModel.title.ilike(kw))
            count_stmt = count_stmt.where(QuestionSetModel.title.ilike(kw))

        total = session.execute(count_stmt).scalar() or 0
        items = list(session.execute(stmt.order_by(QuestionSetModel.created_at.desc()).offset(offset).limit(limit)).scalars().all())
        return items, total

    def get_question_set_by_id(self, session: Any, set_id: int) -> QuestionSetModel | None:
        return session.get(QuestionSetModel, set_id)

    def get_question_set_questions(self, session: Any, set_id: int) -> list[QuestionBankModel]:
        item_stmt = (
            select(QuestionSetItemModel)
            .where(QuestionSetItemModel.set_id == set_id)
            .order_by(QuestionSetItemModel.order_index.asc())
        )
        items = list(session.execute(item_stmt).scalars().all())
        if not items:
            return []
        qids = [it.question_id for it in items]
        q_rows = list(session.execute(select(QuestionBankModel).where(QuestionBankModel.question_id.in_(qids))).scalars().all())
        q_dict = {q.question_id: q for q in q_rows}
        return [q_dict[qid] for qid in qids if qid in q_dict]

    def create_question_set(
        self,
        session: Any,
        *,
        title: str,
        description: str,
        domain_id: int,
        role_id: int | None = None,
        experience_level: str = "junior",
        tech_stack: list[str] | None = None,
        language: str = "vi",
        target_difficulty: int = 3,
        estimated_duration_minutes: int = 20,
        is_curated: bool = True,
        is_active: bool = True,
        question_ids: list[int] | None = None,
    ) -> QuestionSetModel:
        s = QuestionSetModel(
            title=title,
            description=description,
            domain_id=domain_id,
            role_id=role_id,
            experience_level=experience_level,
            tech_stack=tech_stack or [],
            language=language,
            target_difficulty=target_difficulty,
            estimated_duration_minutes=estimated_duration_minutes,
            is_curated=is_curated,
            is_active=is_active,
        )
        session.add(s)
        session.flush()

        if question_ids:
            for idx, qid in enumerate(question_ids):
                item = QuestionSetItemModel(
                    set_id=s.set_id,
                    question_id=qid,
                    order_index=idx,
                )
                session.add(item)

        session.commit()
        session.refresh(s)
        return s

    def update_question_set(
        self,
        session: Any,
        set_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        tech_stack: list[str] | None = None,
        language: str | None = None,
        target_difficulty: int | None = None,
        estimated_duration_minutes: int | None = None,
        is_curated: bool | None = None,
        is_active: bool | None = None,
        question_ids: list[int] | None = None,
    ) -> QuestionSetModel | None:
        s = session.get(QuestionSetModel, set_id)
        if not s:
            return None

        if title is not None:
            s.title = title
        if description is not None:
            s.description = description
        if domain_id is not None:
            s.domain_id = domain_id
        if role_id is not None:
            s.role_id = role_id
        if experience_level is not None:
            s.experience_level = experience_level
        if tech_stack is not None:
            s.tech_stack = tech_stack
        if language is not None:
            s.language = language
        if target_difficulty is not None:
            s.target_difficulty = target_difficulty
        if estimated_duration_minutes is not None:
            s.estimated_duration_minutes = estimated_duration_minutes
        if is_curated is not None:
            s.is_curated = is_curated
        if is_active is not None:
            s.is_active = is_active

        if question_ids is not None:
            existing = session.execute(
                select(QuestionSetItemModel).where(QuestionSetItemModel.set_id == set_id)
            ).scalars().all()
            for it in existing:
                session.delete(it)
            session.flush()

            for idx, qid in enumerate(question_ids):
                item = QuestionSetItemModel(
                    set_id=s.set_id,
                    question_id=qid,
                    order_index=idx,
                )
                session.add(item)

        session.commit()
        session.refresh(s)
        return s

    def delete_question_set(self, session: Any, set_id: int) -> bool:
        s = session.get(QuestionSetModel, set_id)
        if not s:
            return False
        items = session.execute(
            select(QuestionSetItemModel).where(QuestionSetItemModel.set_id == set_id)
        ).scalars().all()
        for it in items:
            session.delete(it)
        session.delete(s)
        session.commit()
        return True
