from __future__ import annotations

from typing import Any
import cloudinary
import cloudinary.uploader

from ...application.storage.ports import StoragePort, UploadedFileResult


class CloudinaryStorageService(StoragePort):
    def __init__(
        self,
        cloud_name: str = "",
        api_key: str = "",
        api_secret: str = "",
        cloudinary_url: str = "",
    ) -> None:
        self.configured = bool((cloud_name and api_key and api_secret) or cloudinary_url)
        if self.configured:
            if cloudinary_url:
                cloudinary.config(cloudinary_url=cloudinary_url, secure=True)
            else:
                cloudinary.config(
                    cloud_name=cloud_name,
                    api_key=api_key,
                    api_secret=api_secret,
                    secure=True,
                )

    def upload(
        self,
        file: Any,
        folder: str = "interviewly",
        resource_type: str = "auto",
        public_id: str | None = None,
    ) -> UploadedFileResult:
        if not self.configured:
            return UploadedFileResult(
                url="",
                secure_url="",
                public_id=public_id or "",
                status="not_configured",
            )
        kwargs: dict[str, Any] = {
            "folder": folder,
            "resource_type": resource_type,
        }
        if public_id:
            kwargs["public_id"] = public_id
        res = cloudinary.uploader.upload(file, **kwargs)
        return UploadedFileResult(
            url=res.get("url", ""),
            secure_url=res.get("secure_url", ""),
            public_id=res.get("public_id", ""),
            format=res.get("format", ""),
            resource_type=res.get("resource_type", resource_type),
            bytes=int(res.get("bytes", 0)),
            status="success",
        )
