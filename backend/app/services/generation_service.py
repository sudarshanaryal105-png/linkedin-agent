import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import AIJob, GeneratedPost, GeneratedPostImage, Prompt, UploadedImage
from app.services import storage
from app.services.ai_pipeline import ImageInput, generate_draft

settings = get_settings()


async def _load_ordered_images(db: AsyncSession, user_id: uuid.UUID, image_ids: list[uuid.UUID]) -> list[UploadedImage]:
    rows = (
        await db.execute(select(UploadedImage).where(UploadedImage.user_id == user_id, UploadedImage.id.in_(image_ids)))
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    missing = [str(i) for i in image_ids if i not in by_id]
    if missing:
        raise ValueError(f"Image id(s) not found or not owned by user: {missing}")
    return [by_id[i] for i in image_ids]


async def start_generation(
    db: AsyncSession,
    user_id: uuid.UUID,
    prompt_text: str,
    optional_context: str | None,
    image_ids: list[uuid.UUID],
) -> tuple[AIJob, list[uuid.UUID]]:
    """Creates the Prompt + AIJob rows synchronously (fast, DB-only). The caller schedules
    `run_generation_job` as a background task to do the actual (slow) AI call.
    """
    images = await _load_ordered_images(db, user_id, image_ids)

    prompt = Prompt(user_id=user_id, raw_text=prompt_text, optional_context=optional_context)
    db.add(prompt)
    await db.flush()

    for image in images:
        image.prompt_id = prompt.id

    job = AIJob(user_id=user_id, prompt_id=prompt.id, job_type="GENERATE_POST", status="PENDING")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job, [image.id for image in images]


async def run_generation_job(job_id: uuid.UUID, user_id: uuid.UUID, image_ids_ordered: list[uuid.UUID]) -> None:
    """Runs in a FastAPI BackgroundTask, after the HTTP response for /api/generate is already
    sent — so it opens its own DB session rather than reusing the request-scoped one.
    """
    async with SessionLocal() as db:
        job = await db.get(AIJob, job_id)
        prompt = await db.get(Prompt, job.prompt_id)
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            images = await _load_ordered_images(db, user_id, image_ids_ordered)
            image_inputs = [ImageInput(bytes_=storage.download_image(img.storage_path), mime_type=img.mime_type) for img in images]

            result = generate_draft(prompt.raw_text, prompt.optional_context, image_inputs)

            post = GeneratedPost(
                prompt_id=prompt.id,
                user_id=user_id,
                ai_job_id=job.id,
                post_text=result.post_text,
                hashtags=result.hashtags,
                status="DRAFT",
                version=1,
            )
            db.add(post)
            await db.flush()

            for order, idx in enumerate(result.selected_image_indexes):
                if 0 <= idx < len(images):
                    db.add(GeneratedPostImage(generated_post_id=post.id, uploaded_image_id=images[idx].id, sort_order=order))

            job.status = "SUCCEEDED"
            job.model_used = settings.anthropic_model
            job.input_tokens = result.input_tokens
            job.output_tokens = result.output_tokens
            job.cost_usd = result.cost_usd
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - persisted for the user, not swallowed
            job.status = "FAILED"
            job.error_message = str(exc)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def run_regeneration_job(job_id: uuid.UUID, user_id: uuid.UUID, post_id: uuid.UUID, feedback: str | None) -> None:
    async with SessionLocal() as db:
        job = await db.get(AIJob, job_id)
        prompt = await db.get(Prompt, job.prompt_id)
        post = await db.get(GeneratedPost, post_id)
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            existing_links = (
                await db.execute(select(GeneratedPostImage).where(GeneratedPostImage.generated_post_id == post_id).order_by(GeneratedPostImage.sort_order))
            ).scalars().all()
            image_ids_ordered = [link.uploaded_image_id for link in existing_links]
            images = await _load_ordered_images(db, user_id, image_ids_ordered) if image_ids_ordered else []
            image_inputs = [ImageInput(bytes_=storage.download_image(img.storage_path), mime_type=img.mime_type) for img in images]

            result = generate_draft(
                prompt.raw_text,
                prompt.optional_context,
                image_inputs,
                prior_draft=post.post_text,
                feedback=feedback or "Improve the draft.",
            )

            post.post_text = result.post_text
            post.hashtags = result.hashtags
            post.status = "DRAFT"
            post.version += 1
            post.ai_job_id = job.id

            for link in existing_links:
                await db.delete(link)
            await db.flush()
            for order, idx in enumerate(result.selected_image_indexes):
                if 0 <= idx < len(images):
                    db.add(GeneratedPostImage(generated_post_id=post.id, uploaded_image_id=images[idx].id, sort_order=order))

            job.status = "SUCCEEDED"
            job.model_used = settings.anthropic_model
            job.input_tokens = result.input_tokens
            job.output_tokens = result.output_tokens
            job.cost_usd = result.cost_usd
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            job.status = "FAILED"
            job.error_message = str(exc)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
