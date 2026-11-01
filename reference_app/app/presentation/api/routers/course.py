from __future__ import annotations

from typing import Any
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ....application.container import ServiceContainer
from ....application.voice.entitlement import check_user_voice_entitlement
from ....infrastructure.persistence.models.user import User
from ..dependencies import get_container, get_optional_user_id, get_session
from ..schemas.course import CourseDetailOut, CourseOut, LessonOut

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


def sanitize_course_html(html_str: str | None) -> str | None:
    if not html_str or not html_str.strip():
        return None
    try:
        soup = BeautifulSoup(html_str, "html.parser")
        disallowed_tags = [
            "script", "style", "iframe", "object", "embed", "form",
            "input", "button", "link", "meta", "base", "applet",
        ]
        for tag in soup.find_all(disallowed_tags):
            tag.decompose()
        for tag in soup.find_all(True):
            attrs = dict(tag.attrs)
            for attr, val in attrs.items():
                attr_lower = attr.lower()
                if attr_lower.startswith("on") or attr_lower in ("formaction", "action"):
                    del tag.attrs[attr]
                elif isinstance(val, str) and val.strip().lower().startswith("javascript:"):
                    del tag.attrs[attr]
        return str(soup)
    except Exception:
        return None


def sanitize_media_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower.startswith("javascript:") or lower.startswith("data:"):
        return None
    if lower.startswith("https://") or lower.startswith("http://") or lower.startswith("/"):
        return cleaned
    return None


def check_user_course_entitlement(session: Any, user_id: int | None) -> bool:
    if not session or not user_id or user_id <= 0:
        return False
    try:
        user = session.get(User, user_id)
        if user:
            role_val = getattr(user.role, "value", str(user.role)) if user.role else ""
            if role_val.lower() in ("admin", "pro"):
                return True
        return check_user_voice_entitlement(session, user_id)
    except Exception:
        return False


def _clean_lesson(ls: Any, is_authorized: bool = False) -> LessonOut:
    raw = LessonOut.model_validate(ls)
    if not raw.is_free and not is_authorized:
        # Strip locked lesson content (Gate G1)
        return LessonOut(
            lesson_id=raw.lesson_id,
            chapter_id=raw.chapter_id,
            title=raw.title,
            duration_minutes=raw.duration_minutes,
            type=raw.type,
            is_free=raw.is_free,
            order_index=raw.order_index,
            video_url=None,
            video_file_name=None,
            video_size=None,
            content_html=None,
            practice_question=None,
            created_at=raw.created_at,
        )
    return LessonOut(
        lesson_id=raw.lesson_id,
        chapter_id=raw.chapter_id,
        title=raw.title,
        duration_minutes=raw.duration_minutes,
        type=raw.type,
        is_free=raw.is_free,
        order_index=raw.order_index,
        video_url=sanitize_media_url(raw.video_url),
        video_file_name=raw.video_file_name,
        video_size=raw.video_size,
        content_html=sanitize_course_html(raw.content_html),
        practice_question=raw.practice_question,
        created_at=raw.created_at,
    )


def _to_course_out(c: Any) -> CourseOut:
    chapter_count = len(c.chapters) if hasattr(c, "chapters") and c.chapters else 0
    lesson_count = (
        sum(len(ch.lessons) for ch in c.chapters if hasattr(ch, "lessons") and ch.lessons)
        if chapter_count
        else 0
    )
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


def _to_course_detail_out(c: Any, is_authorized: bool = False) -> CourseDetailOut:
    base = _to_course_out(c)
    chapters_out = []
    if hasattr(c, "chapters") and c.chapters:
        sorted_chapters = sorted(c.chapters, key=lambda ch: ch.order_index or 0)
        for ch in sorted_chapters:
            lessons_out = []
            if hasattr(ch, "lessons") and ch.lessons:
                sorted_lessons = sorted(ch.lessons, key=lambda ls: ls.order_index or 0)
                for ls in sorted_lessons:
                    lessons_out.append(_clean_lesson(ls, is_authorized=is_authorized))
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
    type: str | None = Query(None),
    role: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    category_val = category if isinstance(category, str) else None
    level_val = level if isinstance(level, str) else None
    type_val = type if isinstance(type, str) else None
    role_val = role if isinstance(role, str) else None
    search_val = search if isinstance(search, str) else None
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0

    items, total = container.course_service.list_courses(
        session,
        category=category_val,
        level=level_val,
        type=type_val,
        role=role_val,
        search=search_val,
        is_active=True,
        limit=limit_val,
        offset=offset_val,
    )
    return {
        "items": [_to_course_out(c) for c in items],
        "total": total,
        "limit": limit_val,
        "offset": offset_val,
    }


@router.get("/{slug_or_id}", response_model=CourseDetailOut)
def get_course_detail(
    slug_or_id: str,
    user_id: int | None = Depends(get_optional_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CourseDetailOut:
    if slug_or_id.isdigit():
        c = container.course_service.get_course_by_id(session, int(slug_or_id))
    else:
        c = container.course_service.get_course_by_slug(session, slug_or_id)

    if not c or not c.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại")

    is_authorized = check_user_course_entitlement(session, user_id)
    return _to_course_detail_out(c, is_authorized=is_authorized)


@router.get("/{slug_or_id}/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson_detail(
    slug_or_id: str,
    lesson_id: int,
    user_id: int | None = Depends(get_optional_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> LessonOut:
    if slug_or_id.isdigit():
        c = container.course_service.get_course_by_id(session, int(slug_or_id))
    else:
        c = container.course_service.get_course_by_slug(session, slug_or_id)

    if not c or not c.is_active:
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

    is_authorized = check_user_course_entitlement(session, user_id)
    if not found_lesson.is_free:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Vui lòng đăng nhập để truy cập bài học này.",
            )
        if not is_authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bài học này thuộc gói nâng cấp. Vui lòng đăng ký gói Pro để mở khóa.",
            )

    return _clean_lesson(found_lesson, is_authorized=True)
