import secrets
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.crypto import create_signed_state, encrypt, read_signed_state
from app.db import get_db
from app.models import LinkedInAccount, OAuthToken
from app.services import linkedin_client

router = APIRouter(prefix="/api/linkedin", tags=["linkedin-auth"])
settings = get_settings()


@router.get("/status")
async def get_status(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await db.scalar(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user.user_id, LinkedInAccount.status == "active")
    )
    if not account:
        return {"connected": False}
    return {"connected": True, "name": account.linkedin_name, "email": account.linkedin_email}


@router.get("/connect")
async def connect(user: CurrentUser = Depends(get_current_user)):
    """Returns the LinkedIn authorize URL. The frontend navigates the browser there directly
    (a plain fetch can't carry the resulting redirect), so this returns JSON rather than
    issuing a 302 itself.
    """
    state = create_signed_state({"user_id": str(user.user_id), "nonce": secrets.token_urlsafe(16)})
    return {"authorize_url": linkedin_client.build_authorize_url(state)}


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    def redirect(status_: str, message: str = "") -> RedirectResponse:
        url = f"{settings.frontend_url}/connect-linkedin?status={status_}"
        if message:
            url += f"&message={message}"
        return RedirectResponse(url)

    if error:
        return redirect("error", "linkedin_denied")
    if not code or not state:
        return redirect("error", "missing_code_or_state")

    payload = read_signed_state(state)
    if not payload:
        return redirect("error", "invalid_or_expired_state")
    user_id = uuid.UUID(payload["user_id"])

    try:
        tokens = linkedin_client.exchange_code_for_token(code)
        userinfo = linkedin_client.get_userinfo(tokens.access_token)
    except linkedin_client.LinkedInAPIError:
        return redirect("error", "linkedin_api_error")

    member_urn = f"urn:li:person:{userinfo['sub']}"

    existing = await db.scalar(select(LinkedInAccount).where(LinkedInAccount.user_id == user_id))
    if existing:
        existing.linkedin_member_urn = member_urn
        existing.linkedin_name = userinfo.get("name")
        existing.linkedin_email = userinfo.get("email")
        existing.status = "active"
        account = existing
    else:
        account = LinkedInAccount(
            user_id=user_id,
            linkedin_member_urn=member_urn,
            linkedin_name=userinfo.get("name"),
            linkedin_email=userinfo.get("email"),
        )
        db.add(account)
    await db.flush()

    existing_token = await db.scalar(select(OAuthToken).where(OAuthToken.linkedin_account_id == account.id))
    if existing_token:
        db.delete(existing_token)
        await db.flush()

    db.add(
        OAuthToken(
            linkedin_account_id=account.id,
            access_token_encrypted=encrypt(tokens.access_token),
            refresh_token_encrypted=encrypt(tokens.refresh_token) if tokens.refresh_token else None,
            access_token_expires_at=tokens.access_token_expires_at,
            refresh_token_expires_at=tokens.refresh_token_expires_at,
            scopes=tokens.scopes,
        )
    )
    await db.commit()

    return redirect("success")
