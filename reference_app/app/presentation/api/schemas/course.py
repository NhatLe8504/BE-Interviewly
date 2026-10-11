from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lesson_id: int
    chapter_id: int
    title: str
    duration_minutes: int = 10
    type: str = "reading"
    is_free: bool = False
    order_index: int = 0
    video_url: str | None = None
    video_file_name: str | None = None
    video_size: str | None = None
    content_html: str | None = None
    practice_question: dict[str, Any] | None = None
    created_at: datetime | str | None = None


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    course_id: int
    title: str
    title_en: str | None = None
    description: str | None = None
    order_index: int = 0
    lesson_count: int = 0


class ChapterDetailOut(ChapterOut):
    lessons: list[LessonOut] = []


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    title: str
    slug: str
    type: str = "Course"
    category: str = "Engineering"
    role: str = "Software Engineer"
    level: str = "all"
    level_label: str | None = None
    estimated_hours: int = 10
    description: str = ""
    target_companies: list[str] = []
    skills: list[str] = []
    highlights: list[str] = []
    image: str | None = None
    is_active: bool = True
    chapter_count: int = 0
    lesson_count: int = 0
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class CourseDetailOut(CourseOut):
    chapters: list[ChapterDetailOut] = []


class CourseCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    type: str = Field("Course", max_length=50)
    category: str = Field("Engineering", max_length=100)
    role: str = Field("Software Engineer", max_length=100)
    level: str = Field("all", max_length=50)
    level_label: str | None = Field(None, max_length=100)
    estimated_hours: int = Field(10, ge=1, le=500)
    description: str = Field("", min_length=0)
    target_companies: list[str] = []
    skills: list[str] = []
    highlights: list[str] = []
    image: str | None = None
    is_active: bool = True


class CourseUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    type: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=100)
    role: str | None = Field(None, max_length=100)
    level: str | None = Field(None, max_length=50)
    level_label: str | None = Field(None, max_length=100)
    estimated_hours: int | None = Field(None, ge=1, le=500)
    description: str | None = None
    target_companies: list[str] | None = None
    skills: list[str] | None = None
    highlights: list[str] | None = None
    image: str | None = None
    is_active: bool | None = None


class ChapterCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    title_en: str | None = Field(None, max_length=255)
    description: str | None = None
    order_index: int | None = 0


class ChapterUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    title_en: str | None = Field(None, max_length=255)
    description: str | None = None
    order_index: int | None = None


class LessonCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    duration_minutes: int = Field(10, ge=1, le=600)
    type: str = Field("reading", max_length=50)
    is_free: bool = False
    order_index: int | None = 0
    video_url: str | None = None
    video_file_name: str | None = None
    video_size: str | None = None
    content_html: str | None = None
    practice_question: dict[str, Any] | None = None


class LessonUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    duration_minutes: int | None = Field(None, ge=1, le=600)
    type: str | None = Field(None, max_length=50)
    is_free: bool | None = None
    order_index: int | None = None
    video_url: str | None = None
    video_file_name: str | None = None
    video_size: str | None = None
    content_html: str | None = None
    practice_question: dict[str, Any] | None = None
