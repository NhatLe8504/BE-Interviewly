from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ....application.container import ServiceContainer
from ..dependencies import get_container, get_session
from ..schemas.course import CourseDetailOut, CourseOut, LessonOut

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


def _to_course_out(c: Any) -> CourseOut:
    chapter_count = len(c.chapters) if hasattr(c, "chapters") and c.chapters else 0
    lesson_count = sum(len(ch.lessons) for ch in c.chapters if hasattr(ch, "lessons") and ch.lessons) if chapter_count else 0
    return CourseOut(
        course_id=c.course_id,
        title=c.title,
        slug=c.slug,
        type=c.type,
        category=c.category,
        role=c.role,
        level=c.level,
        level_label=c.level_label,
        estimated_hours=c.estimated_hours,
        description=c.description,
        target_companies=c.target_companies or [],
        skills=c.skills or [],
        highlights=c.highlights or [],
        image=c.image,
        is_active=c.is_active,
        chapter_count=chapter_count,
        lesson_count=lesson_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_course_detail_out(c: Any) -> CourseDetailOut:
    base = _to_course_out(c)
    chapters_out = []
    if hasattr(c, "chapters") and c.chapters:
        for ch in c.chapters:
            lessons_out = []
            if hasattr(ch, "lessons") and ch.lessons:
                for ls in ch.lessons:
                    lessons_out.append(LessonOut.model_validate(ls))
            chapters_out.append({
                "chapter_id": ch.chapter_id,
                "course_id": ch.course_id,
                "title": ch.title,
                "title_en": ch.title_en,
                "description": ch.description,
                "order_index": ch.order_index,
                "lesson_count": len(lessons_out),
                "lessons": lessons_out,
            })
    return CourseDetailOut(
        **base.model_dump(),
        chapters=chapters_out,
    )


@router.get("", response_model=dict[str, Any])
def list_courses(
    category: str | None = Query(None),
    level: str | None = Query(None),
    role: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    items, total = container.course_service.list_courses(
        session,
        category=category,
        level=level,
        role=role,
        search=search,
        is_active=True,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_to_course_out(c) for c in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{slug_or_id}", response_model=CourseDetailOut)
def get_course_detail(
    slug_or_id: str,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CourseDetailOut:
    if slug_or_id.isdigit():
        c = container.course_service.get_course_by_id(session, int(slug_or_id))
    else:
        c = container.course_service.get_course_by_slug(session, slug_or_id)

    if not c or not c.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại")

    return _to_course_detail_out(c)


@router.get("/{slug_or_id}/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson_detail(
    slug_or_id: str,
    lesson_id: int,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> LessonOut:
    if slug_or_id.isdigit():
        c = container.course_service.get_course_by_id(session, int(slug_or_id))
    else:
        c = container.course_service.get_course_by_slug(session, slug_or_id)

    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại")

    found_lesson = None
    for ch in c.chapters:
        for ls in ch.lessons:
            if ls.lesson_id == lesson_id:
                found_lesson = ls
                break
        if found_lesson:
            break

    if not found_lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bài học không tồn tại")

    return LessonOut.model_validate(found_lesson)
