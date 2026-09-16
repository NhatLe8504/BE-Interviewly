from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class UploadedFileResult:
    url: str
    secure_url: str
    public_id: str
    format: str = ""
    resource_type: str = "auto"
    bytes: int = 0
    status: str = "success"


class StoragePort(Protocol):
    def upload(
        self,
        file: Any,
        folder: str = "interviewly",
        resource_type: str = "auto",
        public_id: str | None = None,
    ) -> UploadedFileResult:
        ...
