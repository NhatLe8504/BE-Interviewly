from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from ...domain.interview import InterviewSession, InterviewTurn


class InterviewSessionRepoPort(Protocol):
    def create(self, session: Any, data: InterviewSession) -> InterviewSession:
        ...

    def find_by_id(self, session: Any, session_id: int) -> InterviewSession | None:
        ...

    def update(self, session: Any, data: InterviewSession) -> InterviewSession:
        ...

    def list_by_user(self, session: Any, user_id: int) -> list[InterviewSession]:
        ...


class InterviewTurnRepoPort(Protocol):
    def add_turn(self, session: Any, turn: InterviewTurn) -> InterviewTurn:
        ...

    def find_by_session_id(self, session: Any, session_id: int) -> list[InterviewTurn]:
        ...

    def find_turn(self, session: Any, session_id: int, turn_number: int) -> InterviewTurn | None:
        ...

    def update_turn(self, session: Any, turn: InterviewTurn) -> InterviewTurn:
        ...


class LLMInterviewerPort(Protocol):
    def generate_first_question(
        self, role: str, level: str, language: str = "vi",
    ) -> str:
        ...

    def generate_follow_up(
        self,
        history: list[dict[str, str]],
        last_question: str,
        last_answer: str,
        turn_number: int,
        role: str,
        level: str,
        language: str = "vi",
        is_final_turn: bool = False,
    ) -> str:
        ...

    def stream_question(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        ...
