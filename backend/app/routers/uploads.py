from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import UploadedImage
from app.schemas import UploadedImageOut
from app.services import storage
from app.services.images import InvalidImageError, validate_and_normalize

router = APIRouter(prefix="/api/upload", tags=["uploads"])
settings = get_settings()


@router.post("", response_model=list[UploadedImageOut])
async def upload_images(
    files: list[UploadFile],
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(files) > settings.max_images_per_generation:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Too many images in one request (max {settings.max_images_per_generation})",
        )

    results: list[UploadedImage] = []
    for file in files:
        raw = await file.read()
        if len(raw) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{file.filename} exceeds {settings.max_upload_mb}MB limit")

        try:
            clean_bytes, mime_type, extension, width, height = validate_and_normalize(raw)
        except InvalidImageError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{file.filename}: {exc}") from exc

        storage_path = storage.upload_image(user.user_id, clean_bytes, mime_type, extension)

        record = UploadedImage(
            user_id=user.user_id,
            prompt_id=None,
            storage_path=storage_path,
            mime_type=mime_type,
            size_bytes=len(clean_bytes),
            width=width,
            height=height,
        )
        db.add(record)
        results.append(record)

    await db.commit()
    for record in results:
        await db.refresh(record)
    return results
