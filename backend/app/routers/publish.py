from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import GeneratedPost, GeneratedPostImage, LinkedInAccount, LinkedInPost, UploadedImage
from app.schemas import PublishRequest, PublishResult
from app.services import linkedin_account, linkedin_client, storage

router = APIRouter(prefix="/api/linkedin", tags=["publish"])


@router.post("/publish", response_model=PublishResult)
async def publish(
    body: PublishRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(GeneratedPost, body.post_id)
    if not post or post.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

    # Already published: return the existing result instead of erroring, so a duplicate
    # click (or a retry after a slow-but-successful prior attempt) is a safe no-op.
    existing = await db.scalar(select(LinkedInPost).where(LinkedInPost.generated_post_id == post.id))
    if existing:
        return PublishResult(post_id=post.id, linkedin_post_urn=existing.linkedin_post_urn, linkedin_permalink=existing.linkedin_permalink)

    # Hard approval gate: only a post the user explicitly approved (or a previously failed
    # publish attempt on already-approved content) can be published. This atomic conditional
    # update is also what prevents two concurrent publish clicks from both proceeding.
    result = await db.execute(
        update(GeneratedPost)
        .where(GeneratedPost.id == post.id, GeneratedPost.status.in_(["APPROVED", "FAILED"]))
        .values(status="PUBLISHING")
        .returning(GeneratedPost.id)
    )
    if result.first() is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Post must be APPROVED to publish (current status: {post.status})")
    await db.commit()

    try:
        access_token, person_urn = await linkedin_account.get_valid_access_token(db, user.user_id)
    except linkedin_account.LinkedInNotConnectedError as exc:
        await _mark_failed(db, post.id, "LinkedIn account not connected")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your LinkedIn account before publishing") from exc
    except linkedin_account.LinkedInReauthRequiredError as exc:
        await _mark_failed(db, post.id, "LinkedIn authorization expired")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your LinkedIn connection expired, please reconnect") from exc

    links = (
        await db.execute(
            select(GeneratedPostImage).where(GeneratedPostImage.generated_post_id == post.id).order_by(GeneratedPostImage.sort_order)
        )
    ).scalars().all()
    images = [await db.get(UploadedImage, link.uploaded_image_id) for link in links]

    try:
        image_urns = [
            linkedin_client.upload_image(access_token, person_urn, storage.download_image(img.storage_path)) for img in images
        ]
        commentary = post.post_text.rstrip()
        if post.hashtags:
            commentary += "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in post.hashtags)

        post_urn, permalink = linkedin_client.create_post(access_token, person_urn, commentary, image_urns)
    except linkedin_client.LinkedInAPIError as exc:
        await _mark_failed(db, post.id, str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LinkedIn publish failed: {exc}") from exc

    account = await db.scalar(select(LinkedInAccount).where(LinkedInAccount.user_id == user.user_id, LinkedInAccount.status == "active"))
    db.add(
        LinkedInPost(
            generated_post_id=post.id,
            linkedin_account_id=account.id,
            linkedin_post_urn=post_urn,
            linkedin_permalink=permalink,
        )
    )
    post.status = "PUBLISHED"
    await db.commit()

    return PublishResult(post_id=post.id, linkedin_post_urn=post_urn, linkedin_permalink=permalink)


async def _mark_failed(db: AsyncSession, post_id, message: str) -> None:  # noqa: ARG001 - message reserved for future logging
    post = await db.get(GeneratedPost, post_id)
    post.status = "FAILED"
    await db.commit()
