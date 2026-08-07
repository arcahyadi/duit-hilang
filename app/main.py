import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func

from .config import settings
from .database import SessionLocal
from .models import User
from .routes import api, auth, web
from .security import hash_password


def seed_admin() -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(func.lower(User.email) == settings.admin_email.lower()).first()
        if not existing:
            db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password), is_admin=True))
            db.commit()
    finally:
        db.close()


async def csrf_check(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if not origin.startswith(settings.rp_origin):
            return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
    return await call_next(request)


app = FastAPI(title=settings.app_name, version="0.1.0")
app.middleware("http")(csrf_check)

app.include_router(auth.router)
app.include_router(web.router)
app.include_router(api.router)

app.add_event_handler("startup", seed_admin)
