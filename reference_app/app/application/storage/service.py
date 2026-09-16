from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ports import StoragePort, UploadedFileResult


@dataclass
class StorageService:
    storage: StoragePort

    def upload_file(
        self,
        file: Any,
        folder: str = "interviewly",
        resource_type: str = "auto",
        public_id: str | None = None,
    ) -> UploadedFileResult:
        return self.storage.upload(
            file=file,
            folder=folder,
            resource_type=resource_type,
            public_id=public_id,
        )
