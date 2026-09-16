from __future__ import annotations

from pydantic import BaseModel, Field


class StarAnalysisOut(BaseModel):
    situation: bool
    task: bool
    action: bool
    result: bool
    completeness_percentage: float = 0.0


class SpeechMetricsOut(BaseModel):
    wpm: float
    pause_duration: float
    filler_count: int
    filler_words: list[str] = []
    pace_assessment: str
    tips: list[str] = []


class RubricEvaluationOut(BaseModel):
    turn_id: int
    clarity_score: float
    structure_score: float
    evidence_score: float
    overall_score: float
    star_analysis: StarAnalysisOut | None = None
    feedback: str = ""
    sample_better_answer: str = ""
    speech_metrics: SpeechMetricsOut | None = None


class SessionResultOut(BaseModel):
    session_id: int
    candidate_id: int
    avg_clarity: float
    avg_structure: float
    avg_evidence: float
    avg_overall: float
    total_turns: int
    performance_rating: str
    evaluations: list[RubricEvaluationOut] = []
