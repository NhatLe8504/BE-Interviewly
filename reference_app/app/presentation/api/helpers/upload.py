from __future__ import annotations

from typing import Any
from fastapi import HTTPException, UploadFile

from ....application.storage.ports import UploadedFileResult
from ..schemas.upload import UploadOut

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "svg"}
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm", "aac"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "txt"}


def validate_file_upload(
    file: UploadFile,
    max_size_mb: int = 25,
    allowed_extensions: set[str] | None = None,
) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if allowed_extensions is not None:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file extension '.{ext}'. Allowed: {sorted(allowed_extensions)}",
            )

    content = file.file.read()
    max_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum allowed size of {max_size_mb}MB",
        )
    return content


def upload_file_helper(
    storage_service: Any,
    file: UploadFile,
    folder: str = "interviewly",
    resource_type: str = "auto",
    max_size_mb: int = 25,
    allowed_extensions: set[str] | None = None,
) -> UploadOut:
    content = validate_file_upload(
        file=file,
        max_size_mb=max_size_mb,
        allowed_extensions=allowed_extensions,
    )
    if storage_service is None:
        raise HTTPException(status_code=500, detail="Storage service is not configured")

    res: UploadedFileResult = storage_service.upload(
        file=content,
        folder=folder,
        resource_type=resource_type,
    )
    if res.status == "not_configured":
        raise HTTPException(status_code=503, detail="Cloudinary storage credentials are not configured")

    return UploadOut(
        url=res.url,
        secure_url=res.secure_url,
        public_id=res.public_id,
        format=res.format,
        resource_type=res.resource_type,
        bytes=res.bytes,
        status=res.status,
    )
