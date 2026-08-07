import hashlib
import secrets
import time

from passlib.hash import argon2
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def hash_password(password: str) -> str:
    return argon2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return argon2.verify(password, password_hash)
    except ValueError:
        return False


def create_session_token(user_id: str) -> str:
    return serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = serializer.loads(token, max_age=settings.session_max_age)
        return data["uid"]
    except (BadSignature, SignatureExpired):
        return None


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return "ft_" + secrets.token_urlsafe(32)


# Simple in-memory rate limiter: (window_start, count) per key
_ratelimit: dict[str, tuple[float, int]] = {}


def rate_limit(key: str, limit: int, window_seconds: int = 300) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.monotonic()
    start, count = _ratelimit.get(key, (now, 0))
    if now - start > window_seconds:
        start, count = now, 0
    if count >= limit:
        return False
    _ratelimit[key] = (start, count + 1)
    return True


def check_secret_key() -> None:
    """Fail fast in production if SECRET_KEY is the insecure default."""
    if settings.cookie_secure and settings.secret_key == "change-me":
        raise RuntimeError("SECRET_KEY must be set when COOKIE_SECURE=true (production)")
