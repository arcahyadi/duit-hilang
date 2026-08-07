import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import ApiKey, User
from .security import hash_api_key, read_session_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = read_session_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session expired")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_web_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Untuk route web: redirect ke halaman login jika belum login."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    user_id = read_session_token(token)
    if not user_id:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def get_api_user(request: Request, db: Session = Depends(get_db)) -> User:
    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(key)).first()
    if not api_key or api_key.revoked:
        raise HTTPException(status_code=401, detail="Invalid API key")
    api_key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return api_key.user


def require_write_api_key(request: Request, db: Session = Depends(get_db)) -> User:
    """API key yang boleh menulis (write access). Admin yang menentukan saat membuat key."""
    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(key)).first()
    if not api_key or api_key.revoked:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not api_key.write_access:
        raise HTTPException(status_code=403, detail="API key does not have write access")
    api_key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return api_key.user
