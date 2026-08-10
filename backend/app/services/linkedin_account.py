import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt, encrypt
from app.models import LinkedInAccount, OAuthToken
from app.services import linkedin_client

REFRESH_MARGIN = timedelta(days=5)


class LinkedInNotConnectedError(RuntimeError):
    pass


class LinkedInReauthRequiredError(RuntimeError):
    pass


async def get_valid_access_token(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """Returns (access_token, person_urn) for the user's connected LinkedIn account,
    refreshing the access token first if it's close to expiry.
    """
    account = await db.scalar(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user_id, LinkedInAccount.status == "active")
    )
    if not account:
        raise LinkedInNotConnectedError("No connected LinkedIn account for this user")

    token = await db.scalar(select(OAuthToken).where(OAuthToken.linkedin_account_id == account.id))
    if not token:
        raise LinkedInNotConnectedError("No stored LinkedIn token for this account")

    now = datetime.now(timezone.utc)
    if token.access_token_expires_at - now > REFRESH_MARGIN:
        return decrypt(token.access_token_encrypted), account.linkedin_member_urn

    if not token.refresh_token_encrypted:
        raise LinkedInReauthRequiredError("Access token expiring and no refresh token stored")

    try:
        refreshed = linkedin_client.refresh_access_token(decrypt(token.refresh_token_encrypted))
    except linkedin_client.LinkedInAPIError as exc:
        raise LinkedInReauthRequiredError("LinkedIn refused to refresh the token; user must reconnect") from exc

    token.access_token_encrypted = encrypt(refreshed.access_token)
    token.access_token_expires_at = refreshed.access_token_expires_at
    if refreshed.refresh_token:
        token.refresh_token_encrypted = encrypt(refreshed.refresh_token)
        token.refresh_token_expires_at = refreshed.refresh_token_expires_at
    await db.flush()
    await db.commit()

    return refreshed.access_token, account.linkedin_member_urn
