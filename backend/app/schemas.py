import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadedImageOut(BaseModel):
    id: uuid.UUID
    storage_path: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    prompt_text: str
    optional_context: str | None = None
    image_ids: list[uuid.UUID]


class RegenerateRequest(BaseModel):
    feedback: str | None = None


class GenerationJobOut(BaseModel):
    job_id: uuid.UUID
    status: str
    generated_post_id: uuid.UUID | None = None
    error_message: str | None = None


class GeneratedPostOut(BaseModel):
    id: uuid.UUID
    prompt_id: uuid.UUID
    post_text: str
    hashtags: list[str]
    status: str
    version: int
    image_ids: list[uuid.UUID]
    image_urls: list[str]
    created_at: datetime
    updated_at: datetime
    linkedin_permalink: str | None = None

    class Config:
        from_attributes = True


class UpdatePostRequest(BaseModel):
    post_text: str | None = None
    hashtags: list[str] | None = None
    image_ids: list[uuid.UUID] | None = None


class PublishRequest(BaseModel):
    post_id: uuid.UUID


class PublishResult(BaseModel):
    post_id: uuid.UUID
    linkedin_post_urn: str
    linkedin_permalink: str
