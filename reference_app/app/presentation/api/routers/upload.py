from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..dependencies import get_current_user_id, get_storage
from ..helpers.upload import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    upload_file_helper,
)
from ..schemas.upload import UploadOut

router = APIRouter(prefix="/api/v1/upload", tags=["upload"])


@router.post("", response_model=UploadOut)
def upload_file(
    file: UploadFile = File(...),
    folder: str = Form("interviewly/general"),
    resource_type: str = Form("auto"),
    storage: Any = Depends(get_storage),
    _user_id: int = Depends(get_current_user_id),
) -> UploadOut:
    return upload_file_helper(
        storage_service=storage,
        file=file,
        folder=folder,
        resource_type=resource_type,
    )


@router.post("/avatar", response_model=UploadOut)
def upload_avatar(
    file: UploadFile = File(...),
    storage: Any = Depends(get_storage),
    _user_id: int = Depends(get_current_user_id),
) -> UploadOut:
    return upload_file_helper(
        storage_service=storage,
        file=file,
        folder="interviewly/avatars",
        resource_type="image",
        max_size_mb=5,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
    )


@router.post("/audio", response_model=UploadOut)
def upload_audio(
    file: UploadFile = File(...),
    storage: Any = Depends(get_storage),
    _user_id: int = Depends(get_current_user_id),
) -> UploadOut:
    return upload_file_helper(
        storage_service=storage,
        file=file,
        folder="interviewly/audio",
        resource_type="video",  # Cloudinary classifies audio as video resource type
        max_size_mb=25,
        allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
    )


@router.post("/document", response_model=UploadOut)
def upload_document(
    file: UploadFile = File(...),
    storage: Any = Depends(get_storage),
    _user_id: int = Depends(get_current_user_id),
) -> UploadOut:
    return upload_file_helper(
        storage_service=storage,
        file=file,
        folder="interviewly/documents",
        resource_type="raw",
        max_size_mb=15,
        allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    )
