import uuid

import jwt
from fastapi import Header, HTTPException, status

from app.config import get_settings

settings = get_settings()


class CurrentUser:
    def __init__(self, user_id: uuid.UUID, email: str | None):
        self.user_id = user_id
        self.email = email


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Validates the Supabase Auth JWT the frontend attaches as `Authorization: Bearer <token>`.

    The frontend authenticates directly against Supabase Auth (signup/login/session refresh);
    this backend never sees passwords, it only ever verifies the resulting JWT.

    This assumes your Supabase project uses the classic shared "JWT Secret" (HS256) —
    Project Settings -> Data API -> JWT Settings. If the project instead has the newer
    asymmetric "JWT Signing Keys" enabled, swap this for JWKS-based verification
    (Supabase exposes a JWKS endpoint at `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized("Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired session token") from exc

    sub = payload.get("sub")
    if not sub:
        raise _unauthorized("Malformed session token")

    return CurrentUser(user_id=uuid.UUID(sub), email=payload.get("email"))
