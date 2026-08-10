from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    environment: str = "development"

    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str
    supabase_storage_bucket: str = "post-images"

    # Postgres (direct connection, used by SQLAlchemy)
    database_url: str

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-5"

    # LinkedIn
    linkedin_client_id: str
    linkedin_client_secret: str
    linkedin_redirect_uri: str = "http://localhost:8000/api/linkedin/callback"
    linkedin_api_version: str = "202607"

    # Security
    token_encryption_key: str  # 32-byte urlsafe base64 key for Fernet

    # Quotas
    max_upload_mb: int = 15
    max_images_per_generation: int = 6
    daily_generation_quota_per_user: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
