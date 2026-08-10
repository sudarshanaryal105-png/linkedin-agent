import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import AIJob, GeneratedPost, GeneratedPostImage, LinkedInPost, UploadedImage
from app.schemas import GeneratedPostOut, GenerationJobOut, RegenerateRequest, UpdatePostRequest
from app.services import generation_service, storage

router = APIRouter(prefix="/api/posts", tags=["posts"])


async def _get_owned_post(db: AsyncSession, post_id: uuid.UUID, user_id: uuid.UUID) -> GeneratedPost:
    post = await db.get(GeneratedPost, post_id)
    if not post or post.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


async def _to_out(db: AsyncSession, post: GeneratedPost) -> GeneratedPostOut:
    links = (
        await db.execute(
            select(GeneratedPostImage).where(GeneratedPostImage.generated_post_id == post.id).order_by(GeneratedPostImage.sort_order)
        )
    ).scalars().all()
    permalink = None
    if post.status == "PUBLISHED":
        li_post = await db.scalar(select(LinkedInPost).where(LinkedInPost.generated_post_id == post.id))
        permalink = li_post.linkedin_permalink if li_post else None

    image_urls: list[str] = []
    for link in links:
        image = await db.get(UploadedImage, link.uploaded_image_id)
        if image:
            image_urls.append(storage.get_public_url(image.storage_path))

    return GeneratedPostOut(
        id=post.id,
        prompt_id=post.prompt_id,
        post_text=post.post_text,
        hashtags=post.hashtags,
        status=post.status,
        version=post.version,
        image_ids=[link.uploaded_image_id for link in links],
        image_urls=image_urls,
        created_at=post.created_at,
        updated_at=post.updated_at,
        linkedin_permalink=permalink,
    )


@router.get("", response_model=list[GeneratedPostOut])
async def list_posts(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    posts = (
        await db.execute(select(GeneratedPost).where(GeneratedPost.user_id == user.user_id).order_by(GeneratedPost.created_at.desc()))
    ).scalars().all()
    return [await _to_out(db, post) for post in posts]


@router.get("/{post_id}", response_model=GeneratedPostOut)
async def get_post(post_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    post = await _get_owned_post(db, post_id, user.user_id)
    return await _to_out(db, post)


@router.patch("/{post_id}", response_model=GeneratedPostOut)
async def update_post(
    post_id: uuid.UUID,
    body: UpdatePostRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _get_owned_post(db, post_id, user.user_id)
    if post.status in ("PUBLISHING", "PUBLISHED"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot edit a post in status {post.status}")

    if body.post_text is not None:
        post.post_text = body.post_text
    if body.hashtags is not None:
        post.hashtags = body.hashtags
    if body.image_ids is not None:
        existing = (
            await db.execute(select(GeneratedPostImage).where(GeneratedPostImage.generated_post_id == post.id))
        ).scalars().all()
        for link in existing:
            await db.delete(link)
        await db.flush()
        for order, image_id in enumerate(body.image_ids):
            db.add(GeneratedPostImage(generated_post_id=post.id, uploaded_image_id=image_id, sort_order=order))

    # Any edit invalidates a prior approval: a stale approval must never be replayable
    # against content the user has since changed.
    post.status = "EDITED"
    await db.commit()
    await db.refresh(post)
    return await _to_out(db, post)


@router.post("/{post_id}/approve", response_model=GeneratedPostOut)
async def approve_post(post_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    post = await _get_owned_post(db, post_id, user.user_id)
    if post.status not in ("DRAFT", "EDITED"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot approve a post in status {post.status}")

    result = await db.execute(
        update(GeneratedPost)
        .where(GeneratedPost.id == post.id, GeneratedPost.status.in_(["DRAFT", "EDITED"]))
        .values(status="APPROVED")
        .returning(GeneratedPost.id)
    )
    if result.first() is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Post status changed concurrently, refresh and try again")
    await db.commit()
    await db.refresh(post)
    return await _to_out(db, post)


@router.post("/{post_id}/regenerate", response_model=GenerationJobOut)
async def regenerate_post(
    post_id: uuid.UUID,
    body: RegenerateRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _get_owned_post(db, post_id, user.user_id)
    if post.status in ("PUBLISHING", "PUBLISHED"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot regenerate a post in status {post.status}")

    job = AIJob(user_id=user.user_id, prompt_id=post.prompt_id, job_type="REGENERATE", status="PENDING")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(generation_service.run_regeneration_job, job.id, user.user_id, post.id, body.feedback)
    return GenerationJobOut(job_id=job.id, status=job.status)
