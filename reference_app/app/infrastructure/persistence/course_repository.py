from __future__ import annotations

import re
import unicodedata
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .models.course import Course, CourseChapter, CourseLesson


def slugify(text: str) -> str:
    slug = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^\w\s-]", "", slug).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "course"


class CourseRepository:
    def list_courses(
        self,
        session: Any,
        *,
        category: str | None = None,
        level: str | None = None,
        role: str | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        stmt = select(Course)
        if is_active is not None:
            stmt = stmt.where(Course.is_active == is_active)
        if category and category != "all":
            stmt = stmt.where(Course.category.ilike(f"%{category}%"))
        if level and level != "all":
            stmt = stmt.where(Course.level == level)
        if role and role != "all":
            stmt = stmt.where(Course.role.ilike(f"%{role}%"))
        if search and search.strip():
            kw = f"%{search.strip()}%"
            stmt = stmt.where(Course.title.ilike(kw) | Course.description.ilike(kw))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = session.execute(count_stmt).scalar() or 0

        stmt = stmt.options(
            selectinload(Course.chapters).selectinload(CourseChapter.lessons)
        ).order_by(Course.created_at.desc()).limit(limit).offset(offset)

        items = list(session.execute(stmt).scalars().all())
        return items, total

    def get_course_by_id(self, session: Any, course_id: int) -> Course | None:
        stmt = (
            select(Course)
            .where(Course.course_id == course_id)
            .options(selectinload(Course.chapters).selectinload(CourseChapter.lessons))
        )
        return session.execute(stmt).scalar_one_or_none()

    def get_course_by_slug(self, session: Any, slug: str) -> Course | None:
        stmt = (
            select(Course)
            .where(Course.slug == slug)
            .options(selectinload(Course.chapters).selectinload(CourseChapter.lessons))
        )
        return session.execute(stmt).scalar_one_or_none()

    def create_course(self, session: Any, data: dict[str, Any]) -> Course:
        slug = data.get("slug")
        if not slug or not slug.strip():
            base_slug = slugify(data.get("title", "course"))
            slug = base_slug
            idx = 1
            while self.get_course_by_slug(session, slug):
                slug = f"{base_slug}-{idx}"
                idx += 1
        data["slug"] = slug

        course = Course(
            title=data["title"],
            slug=data["slug"],
            type=data.get("type", "Course"),
            category=data.get("category", "Engineering"),
            role=data.get("role", "Software Engineer"),
            level=data.get("level", "all"),
            level_label=data.get("level_label"),
            estimated_hours=data.get("estimated_hours", 10),
            description=data.get("description", ""),
            target_companies=data.get("target_companies", []),
            skills=data.get("skills", []),
            highlights=data.get("highlights", []),
            image=data.get("image"),
            is_active=data.get("is_active", True),
        )
        session.add(course)
        session.commit()
        session.refresh(course)
        return course

    def update_course(self, session: Any, course_id: int, data: dict[str, Any]) -> Course | None:
        course = self.get_course_by_id(session, course_id)
        if not course:
            return None

        for field, value in data.items():
            if value is not None and hasattr(course, field):
                setattr(course, field, value)

        session.commit()
        session.refresh(course)
        return course

    def delete_course(self, session: Any, course_id: int) -> bool:
        course = self.get_course_by_id(session, course_id)
        if not course:
            return False
        session.delete(course)
        session.commit()
        return True

    # Chapters
    def create_chapter(self, session: Any, course_id: int, data: dict[str, Any]) -> CourseChapter | None:
        course = self.get_course_by_id(session, course_id)
        if not course:
            return None

        order_idx = data.get("order_index")
        if order_idx is None:
            max_order = (
                session.execute(
                    select(func.max(CourseChapter.order_index)).where(CourseChapter.course_id == course_id)
                ).scalar()
                or 0
            )
            order_idx = max_order + 1

        chapter = CourseChapter(
            course_id=course_id,
            title=data["title"],
            title_en=data.get("title_en"),
            description=data.get("description"),
            order_index=order_idx,
        )
        session.add(chapter)
        session.commit()
        session.refresh(chapter)
        return chapter

    def update_chapter(self, session: Any, chapter_id: int, data: dict[str, Any]) -> CourseChapter | None:
        stmt = select(CourseChapter).where(CourseChapter.chapter_id == chapter_id)
        chapter = session.execute(stmt).scalar_one_or_none()
        if not chapter:
            return None

        for field, value in data.items():
            if value is not None and hasattr(chapter, field):
                setattr(chapter, field, value)

        session.commit()
        session.refresh(chapter)
        return chapter

    def delete_chapter(self, session: Any, chapter_id: int) -> bool:
        stmt = select(CourseChapter).where(CourseChapter.chapter_id == chapter_id)
        chapter = session.execute(stmt).scalar_one_or_none()
        if not chapter:
            return False
        session.delete(chapter)
        session.commit()
        return True

    # Lessons
    def create_lesson(self, session: Any, chapter_id: int, data: dict[str, Any]) -> CourseLesson | None:
        stmt = select(CourseChapter).where(CourseChapter.chapter_id == chapter_id)
        chapter = session.execute(stmt).scalar_one_or_none()
        if not chapter:
            return None

        order_idx = data.get("order_index")
        if order_idx is None:
            max_order = (
                session.execute(
                    select(func.max(CourseLesson.order_index)).where(CourseLesson.chapter_id == chapter_id)
                ).scalar()
                or 0
            )
            order_idx = max_order + 1

        lesson = CourseLesson(
            chapter_id=chapter_id,
            title=data["title"],
            duration_minutes=data.get("duration_minutes", 10),
            type=data.get("type", "reading"),
            is_free=data.get("is_free", False),
            order_index=order_idx,
            video_url=data.get("video_url"),
            video_file_name=data.get("video_file_name"),
            video_size=data.get("video_size"),
            content_html=data.get("content_html"),
            practice_question=data.get("practice_question"),
        )
        session.add(lesson)
        session.commit()
        session.refresh(lesson)
        return lesson

    def update_lesson(self, session: Any, lesson_id: int, data: dict[str, Any]) -> CourseLesson | None:
        stmt = select(CourseLesson).where(CourseLesson.lesson_id == lesson_id)
        lesson = session.execute(stmt).scalar_one_or_none()
        if not lesson:
            return None

        for field, value in data.items():
            if value is not None and hasattr(lesson, field):
                setattr(lesson, field, value)

        session.commit()
        session.refresh(lesson)
        return lesson

    def delete_lesson(self, session: Any, lesson_id: int) -> bool:
        stmt = select(CourseLesson).where(CourseLesson.lesson_id == lesson_id)
        lesson = session.execute(stmt).scalar_one_or_none()
        if not lesson:
            return False
        session.delete(lesson)
        session.commit()
        return True
