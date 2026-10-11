from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        Index("idx_courses_slug", "slug"),
        Index("idx_courses_is_active", "is_active"),
    )

    course_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Course")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Engineering")
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="Software Engineer")
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="all")
    level_label: Mapped[str | None] = mapped_column(String(100))
    estimated_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    highlights: Mapped[list[str]] = mapped_column(JSON, default=list)
    image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(),
    )

    chapters: Mapped[list["CourseChapter"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseChapter.order_index",
    )


class CourseChapter(Base):
    __tablename__ = "course_chapters"
    __table_args__ = (
        Index("idx_course_chapters_course_id", "course_id"),
    )

    chapter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.course_id", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    course: Mapped["Course"] = relationship(back_populates="chapters")
    lessons: Mapped[list["CourseLesson"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="CourseLesson.order_index",
    )


class CourseLesson(Base):
    __tablename__ = "course_lessons"
    __table_args__ = (
        Index("idx_course_lessons_chapter_id", "chapter_id"),
    )

    lesson_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("course_chapters.chapter_id", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="reading")
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_url: Mapped[str | None] = mapped_column(String(500))
    video_file_name: Mapped[str | None] = mapped_column(String(255))
    video_size: Mapped[str | None] = mapped_column(String(50))
    content_html: Mapped[str | None] = mapped_column(Text)
    practice_question: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    chapter: Mapped["CourseChapter"] = relationship(back_populates="lessons")
