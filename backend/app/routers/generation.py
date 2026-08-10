import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import AIJob, GeneratedPost
from app.schemas import GenerateRequest, GenerationJobOut
from app.services import generation_service

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=GenerationJobOut)
async def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.image_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one image is required")

    try:
        job, ordered_image_ids = await generation_service.start_generation(
            db, user.user_id, body.prompt_text, body.optional_context, body.image_ids
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    background_tasks.add_task(generation_service.run_generation_job, job.id, user.user_id, ordered_image_ids)
    return GenerationJobOut(job_id=job.id, status=job.status)


@router.get("/generation/{job_id}", response_model=GenerationJobOut)
async def get_generation(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(AIJob, job_id)
    if not job or job.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    generated_post_id = None
    if job.status == "SUCCEEDED":
        post = await db.scalar(select(GeneratedPost).where(GeneratedPost.ai_job_id == job.id))
        generated_post_id = post.id if post else None

    return GenerationJobOut(job_id=job.id, status=job.status, generated_post_id=generated_post_id, error_message=job.error_message)
