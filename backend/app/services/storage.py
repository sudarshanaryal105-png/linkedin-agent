import uuid
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings

settings = get_settings()


@lru_cache
def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


def upload_image(user_id: uuid.UUID, image_bytes: bytes, mime_type: str, extension: str) -> str:
    """Uploads a re-encoded image to the post-images bucket. Returns the storage path.

    Bucket is public: these images are only ever uploaded in order to be attached to a
    public LinkedIn post, so there is no confidentiality requirement on the stored copy.
    """
    path = f"{user_id}/{uuid.uuid4()}.{extension}"
    get_supabase().storage.from_(settings.supabase_storage_bucket).upload(
        path, image_bytes, {"content-type": mime_type}
    )
    return path


def download_image(storage_path: str) -> bytes:
    return get_supabase().storage.from_(settings.supabase_storage_bucket).download(storage_path)


def get_public_url(storage_path: str) -> str:
    return get_supabase().storage.from_(settings.supabase_storage_bucket).get_public_url(storage_path)
