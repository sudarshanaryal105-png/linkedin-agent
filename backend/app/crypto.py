import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_settings = get_settings()
_fernet = Fernet(_settings.token_encryption_key.encode())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


def create_signed_state(payload: dict) -> str:
    """Short-lived, tamper-proof token used as the OAuth `state` param.

    Reuses the app's Fernet key: Fernet tokens are already timestamped and URL-safe,
    which is exactly what's needed to survive a browser redirect round trip and be
    verified for both integrity and expiry on the way back in the callback.
    """
    return _fernet.encrypt(json.dumps(payload).encode()).decode()


def read_signed_state(token: str, max_age_seconds: int = 600) -> dict | None:
    try:
        raw = _fernet.decrypt(token.encode(), ttl=max_age_seconds)
    except InvalidToken:
        return None
    return json.loads(raw.decode())
