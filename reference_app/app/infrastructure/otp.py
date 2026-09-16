from __future__ import annotations

import threading

from ..application.auth.ports import OtpStorePort
from ..domain.identity import OtpRecord


class MemoryOtpStore(OtpStorePort):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[tuple[str, str], OtpRecord] = {}

    def save(self, record: OtpRecord) -> None:
        with self._lock:
            self._records[(record.email, record.purpose)] = record

    def find(self, email: str, purpose: str = "verify_email") -> OtpRecord | None:
        with self._lock:
            return self._records.get((email, purpose))

    def delete(self, email: str, purpose: str = "verify_email") -> None:
        with self._lock:
            self._records.pop((email, purpose), None)
