from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    candidate = "candidate"
    admin = "admin"


class Language(str, enum.Enum):
    vi = "vi"
    en = "en"


class UserStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class ExperienceLevel(str, enum.Enum):
    intern = "intern"
    fresher = "fresher"
    junior = "junior"
    mid = "mid"
    senior = "senior"


class QuestionType(str, enum.Enum):
    behavioral = "behavioral"
    technical = "technical"
    situational = "situational"


class SessionMode(str, enum.Enum):
    text = "text"
    voice = "voice"


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class TurnSpeaker(str, enum.Enum):
    ai = "ai"
    candidate = "candidate"


class BillingCycle(str, enum.Enum):
    free = "free"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class SubStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    refunded = "refunded"


class AuditAction(str, enum.Enum):
    insert = "insert"
    update = "update"
    delete = "delete"

class QuestionModerationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class QuestionSource(str, enum.Enum):
    admin_manual = "admin_manual"
    admin_ai = "admin_ai"
    user_ai = "user_ai"
    user_manual = "user_manual"

