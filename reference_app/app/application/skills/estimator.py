from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from .taxonomy import get_default_taxonomy


@dataclass
class EvidenceInput:
    skill_id: str
    score: float  # 0.0 to 1.0
    difficulty: int  # 1 to 5
    grader_confidence: float  # 0.0 to 1.0
    source_type: str  # interview_turn, practice_history, etc.
    created_at: datetime


@dataclass
class SkillEstimateResult:
    skill_id: str
    ability_score: float  # 0.0 to 5.0
    level: str  # none, beginner, junior, middle, senior, lead
    confidence: float  # 0.0 to 1.0
    evidence_count: int
    max_difficulty_passed: int
    last_evidence_at: datetime | None


@dataclass
class CareerProfileResult:
    primary_role_track: str
    secondary_role_track: str | None
    role_confidence: float
    overall_level: str
    top_skills: list[dict[str, Any]]
    weak_skills: list[dict[str, Any]]


class SkillLevelEstimator:
    K_FACTOR = 0.60
    HALF_LIFE_DAYS = 90.0

    SOURCE_WEIGHTS = {
        "interview_turn": 1.0,
        "practice_history": 0.85,
        "jd_interview": 1.0,
        "self_declared": 0.3,
    }

    @classmethod
    def estimate_skill(
        cls,
        skill_id: str,
        evidences: list[EvidenceInput],
        now: datetime | None = None,
    ) -> SkillEstimateResult:
        if not evidences:
            return SkillEstimateResult(
                skill_id=skill_id,
                ability_score=1.0,
                level="none",
                confidence=0.0,
                evidence_count=0,
                max_difficulty_passed=0,
                last_evidence_at=None,
            )

        if now is None:
            now = datetime.now(timezone.utc)

        # Sort by creation date
        sorted_evs = sorted(evidences, key=lambda e: e.created_at)

        theta = 1.0  # Initial prior ability
        max_diff_passed = 0
        total_effective_weight = 0.0

        for ev in sorted_evs:
            # Check difficulty passed
            if ev.score >= 0.60 and ev.difficulty > max_diff_passed:
                max_diff_passed = ev.difficulty

            # Days since evidence
            ev_dt = ev.created_at if ev.created_at.tzinfo else ev.created_at.replace(tzinfo=timezone.utc)
            now_dt = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            days_ago = max(0.0, (now_dt - ev_dt).total_seconds() / 86400.0)

            # Recency decay (half-life of 90 days)
            recency = 0.5 ** (days_ago / cls.HALF_LIFE_DAYS)
            source_weight = cls.SOURCE_WEIGHTS.get(ev.source_type, 0.8)
            w = max(0.05, ev.grader_confidence * recency * source_weight)
            total_effective_weight += w

            # Logistic expected probability of success given current theta and question difficulty
            expected = 1.0 / (1.0 + math.exp(-1.2 * (theta - float(ev.difficulty))))

            # Elo-like update
            delta = cls.K_FACTOR * w * (ev.score - expected)
            theta = max(0.0, min(5.0, theta + delta))

        # Ceiling rule: cannot claim Senior (>= 3.2) if never passed difficulty >= 3
        if max_diff_passed < 3 and theta >= 3.2:
            theta = 3.19
        elif max_diff_passed < 2 and theta >= 2.0:
            theta = 1.99

        # Confidence based on accumulated effective weight
        confidence = round(1.0 - math.exp(-total_effective_weight / 3.5), 2)

        # Map theta to level
        level = "none"
        if len(evidences) >= 2 and confidence >= 0.30:
            if theta < 1.0:
                level = "beginner"
            elif theta < 2.0:
                level = "junior"
            elif theta < 3.2:
                level = "middle"
            elif theta < 4.5:
                level = "senior"
            else:
                level = "lead"

        return SkillEstimateResult(
            skill_id=skill_id,
            ability_score=round(theta, 2),
            level=level,
            confidence=confidence,
            evidence_count=len(evidences),
            max_difficulty_passed=max_diff_passed,
            last_evidence_at=sorted_evs[-1].created_at,
        )

    @classmethod
    def estimate_career_profile(
        cls,
        skill_estimates: list[SkillEstimateResult],
    ) -> CareerProfileResult:
        taxonomy = get_default_taxonomy()
        track_scores: dict[str, float] = {
            "backend": 0.0,
            "frontend": 0.0,
            "fullstack": 0.0,
            "devops": 0.0,
            "data": 0.0,
            "mobile": 0.0,
            "ai_ml": 0.0,
            "qa": 0.0,
        }

        # Filter estimates with meaningful confidence
        valid_estimates = [s for s in skill_estimates if s.level != "none" and s.confidence >= 0.25]

        for s in valid_estimates:
            defn = taxonomy.get_skill(s.skill_id)
            if not defn:
                continue
            weight = s.ability_score * s.confidence
            for tr in defn.role_tracks:
                if tr in track_scores:
                    track_scores[tr] += weight

        sorted_tracks = sorted(track_scores.items(), key=lambda x: x[1], reverse=True)
        primary_track = "backend"
        secondary_track = None
        role_confidence = 0.0

        if sorted_tracks and sorted_tracks[0][1] > 0:
            primary_track = sorted_tracks[0][0]
            role_confidence = min(1.0, round(sorted_tracks[0][1] / 10.0, 2))
            if len(sorted_tracks) > 1 and sorted_tracks[1][1] >= 0.70 * sorted_tracks[0][1] and sorted_tracks[1][1] > 0.5:
                secondary_track = sorted_tracks[1][0]

        # Top skills and weak skills
        sorted_by_ability = sorted(valid_estimates, key=lambda s: s.ability_score, reverse=True)
        top_skills = [
            {
                "skill_id": s.skill_id,
                "name": taxonomy.get_skill(s.skill_id).name if taxonomy.get_skill(s.skill_id) else s.skill_id,
                "level": s.level,
                "ability_score": s.ability_score,
                "confidence": s.confidence,
            }
            for s in sorted_by_ability[:6]
        ]

        # Weak skills: skills with evidence but ability < 2.0 or level beginner/junior with gap
        weak_candidates = [
            s for s in valid_estimates
            if s.ability_score < 2.3 and s.evidence_count >= 1
        ]
        weak_candidates = sorted(weak_candidates, key=lambda s: s.ability_score)
        weak_skills = [
            {
                "skill_id": s.skill_id,
                "name": taxonomy.get_skill(s.skill_id).name if taxonomy.get_skill(s.skill_id) else s.skill_id,
                "level": s.level,
                "ability_score": s.ability_score,
                "confidence": s.confidence,
            }
            for s in weak_candidates[:5]
        ]

        # Overall level: median level of top 5 skills in primary track
        track_skills = [
            s for s in sorted_by_ability
            if taxonomy.get_skill(s.skill_id) and primary_track in taxonomy.get_skill(s.skill_id).role_tracks
        ]
        overall_level = "none"
        if track_skills:
            levels = [s.level for s in track_skills[:5]]
            level_rank = {"none": 0, "beginner": 1, "junior": 2, "middle": 3, "senior": 4, "lead": 5}
            sorted_ranks = sorted(level_rank.get(lv, 0) for lv in levels)
            median_rank = sorted_ranks[len(sorted_ranks) // 2]
            rank_to_level = {0: "none", 1: "beginner", 2: "junior", 3: "middle", 4: "senior", 5: "lead"}
            overall_level = rank_to_level.get(median_rank, "junior")

        return CareerProfileResult(
            primary_role_track=primary_track,
            secondary_role_track=secondary_track,
            role_confidence=role_confidence,
            overall_level=overall_level,
            top_skills=top_skills,
            weak_skills=weak_skills,
        )
