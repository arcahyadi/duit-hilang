from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import ApiKey, User
from ..security import generate_api_key, hash_api_key, hash_password
from ..ui import templates

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at).all()
    api_keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin.html", {
        "user": user, "users": users, "api_keys": api_keys,
    })


@router.post("/users")
def user_create(
    email: str = Form(...), password: str = Form(...),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if not email or not password:
        return RedirectResponse("/admin?error=missing", status_code=303)
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse("/admin?error=exists", status_code=303)
    db.add(User(email=email, password_hash=hash_password(password), is_admin=False))
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/delete")
def user_delete(
    user_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target and target.id != user.id:  # cannot delete self
        db.delete(target)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/api-keys")
def api_key_create(
    request: Request,
    name: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin?error=missing", status_code=303)
    key = generate_api_key()
    db.add(ApiKey(user_id=user.id, name=name, key_hash=hash_api_key(key)))
    db.commit()
    users = db.query(User).order_by(User.created_at).all()
    api_keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin.html", {
        "user": user, "users": users, "api_keys": api_keys, "new_key": key,
    })


@router.post("/api-keys/{key_id}/revoke")
def api_key_revoke(
    key_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = db.get(ApiKey, key_id)
    if key:
        key.revoked = True
        db.commit()
    return RedirectResponse("/admin", status_code=303)
