from __future__ import annotations

from pydantic import BaseModel, Field


class UploadOut(BaseModel):
    url: str = Field(description="URL to the uploaded resource")
    secure_url: str = Field(description="HTTPS URL to the uploaded resource")
    public_id: str = Field(description="Public ID in Cloudinary")
    format: str = Field(default="", description="File format")
    resource_type: str = Field(default="auto", description="Resource type: image, video, raw, auto")
    bytes: int = Field(default=0, description="Size in bytes")
    status: str = Field(default="success", description="Upload status")
