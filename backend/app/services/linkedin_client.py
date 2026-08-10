import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings

settings = get_settings()

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
API_BASE = "https://api.linkedin.com/rest"

SCOPES = "openid profile email w_member_social"


class LinkedInAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


@dataclass
class TokenSet:
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str | None
    refresh_token_expires_at: datetime | None
    scopes: list[str]


def _token_set_from_response(payload: dict) -> TokenSet:
    now = datetime.now(timezone.utc)
    refresh_expires_in = payload.get("refresh_token_expires_in")
    return TokenSet(
        access_token=payload["access_token"],
        access_token_expires_at=now + timedelta(seconds=payload["expires_in"]),
        refresh_token=payload.get("refresh_token"),
        refresh_token_expires_at=(now + timedelta(seconds=refresh_expires_in)) if refresh_expires_in else None,
        scopes=payload.get("scope", SCOPES).split(","),
    )


def exchange_code_for_token(code: str) -> TokenSet:
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.linkedin_redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise LinkedInAPIError(f"Token exchange failed: {resp.text}", resp.status_code)
    return _token_set_from_response(resp.json())


def refresh_access_token(refresh_token: str) -> TokenSet:
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise LinkedInAPIError(f"Token refresh failed: {resp.text}", resp.status_code)
    return _token_set_from_response(resp.json())


def get_userinfo(access_token: str) -> dict:
    with httpx.Client(timeout=15) as client:
        resp = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        raise LinkedInAPIError(f"userinfo failed: {resp.text}", resp.status_code)
    return resp.json()  # {sub, name, email, picture, ...}


def _headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": settings.linkedin_api_version,
        "Content-Type": "application/json",
    }


def upload_image(access_token: str, person_urn: str, image_bytes: bytes) -> str:
    """Registers + uploads an image, returns its urn:li:image:{id}."""
    with httpx.Client(timeout=30) as client:
        init_resp = client.post(
            f"{API_BASE}/images?action=initializeUpload",
            headers=_headers(access_token),
            json={"initializeUploadRequest": {"owner": person_urn}},
        )
        if init_resp.status_code != 200:
            raise LinkedInAPIError(f"Image init failed: {init_resp.text}", init_resp.status_code)
        value = init_resp.json()["value"]
        upload_url = value["uploadUrl"]
        image_urn = value["image"]

        put_resp = client.put(upload_url, headers={"Authorization": f"Bearer {access_token}"}, content=image_bytes)
        if put_resp.status_code not in (200, 201):
            raise LinkedInAPIError(f"Image binary upload failed: {put_resp.text}", put_resp.status_code)

    return image_urn


def create_post(access_token: str, person_urn: str, commentary: str, image_urns: list[str]) -> tuple[str, str]:
    """Creates the post. Returns (post_urn, permalink)."""
    body: dict = {
        "author": person_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if len(image_urns) == 1:
        body["content"] = {"media": {"id": image_urns[0]}}
    elif len(image_urns) > 1:
        body["content"] = {"multiImage": {"images": [{"id": urn} for urn in image_urns]}}

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{API_BASE}/posts", headers=_headers(access_token), json=body)

    if resp.status_code != 201:
        raise LinkedInAPIError(f"Post creation failed: {resp.text}", resp.status_code)

    post_urn = resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id")
    if not post_urn:
        raise LinkedInAPIError("Post created but no x-restli-id header returned")

    permalink = f"https://www.linkedin.com/feed/update/{post_urn}/"
    return post_urn, permalink
