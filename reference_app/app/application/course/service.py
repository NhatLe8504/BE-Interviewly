from __future__ import annotations

from typing import Any
from ...infrastructure.persistence.course_repository import CourseRepository
from ...infrastructure.persistence.models.course import Course, CourseChapter, CourseLesson


class CourseService:
    def __init__(self, repo: CourseRepository) -> None:
        self.repo = repo

    def list_courses(
        self,
        session: Any,
        *,
        category: str | None = None,
        level: str | None = None,
        type: str | None = None,
        role: str | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        return self.repo.list_courses(
            session,
            category=category,
            level=level,
            type=type,
            role=role,
            search=search,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

    def get_course_by_id(self, session: Any, course_id: int) -> Course | None:
        return self.repo.get_course_by_id(session, course_id)

    def get_course_by_slug(self, session: Any, slug: str) -> Course | None:
        return self.repo.get_course_by_slug(session, slug)

    def create_course(self, session: Any, data: dict[str, Any]) -> Course:
        return self.repo.create_course(session, data)

    def update_course(self, session: Any, course_id: int, data: dict[str, Any]) -> Course | None:
        return self.repo.update_course(session, course_id, data)

    def delete_course(self, session: Any, course_id: int) -> bool:
        return self.repo.delete_course(session, course_id)

    def create_chapter(self, session: Any, course_id: int, data: dict[str, Any]) -> CourseChapter | None:
        return self.repo.create_chapter(session, course_id, data)

    def update_chapter(self, session: Any, chapter_id: int, data: dict[str, Any]) -> CourseChapter | None:
        return self.repo.update_chapter(session, chapter_id, data)

    def delete_chapter(self, session: Any, chapter_id: int) -> bool:
        return self.repo.delete_chapter(session, chapter_id)

    def create_lesson(self, session: Any, chapter_id: int, data: dict[str, Any]) -> CourseLesson | None:
        return self.repo.create_lesson(session, chapter_id, data)

    def update_lesson(self, session: Any, lesson_id: int, data: dict[str, Any]) -> CourseLesson | None:
        return self.repo.update_lesson(session, lesson_id, data)

    def delete_lesson(self, session: Any, lesson_id: int) -> bool:
        return self.repo.delete_lesson(session, lesson_id)
