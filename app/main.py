import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func

from .config import settings
from .database import SessionLocal
from .models import User
from .routes import admin, api, auth, web
from .security import check_secret_key, hash_password


def seed_admin() -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(func.lower(User.email) == settings.admin_email.lower()).first()
        if not existing:
            db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password), is_admin=True))
            db.commit()
    finally:
        db.close()


def _origin(request: Request) -> str:
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


async def csrf_check(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE"):
        if _origin(request) != settings.rp_origin:
            return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
    return await call_next(request)


async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src https://cdnjs.cloudflare.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return response


app = FastAPI(title=settings.app_name, version="0.1.0")
app.middleware("http")(security_headers)
app.middleware("http")(csrf_check)

app.include_router(auth.router)
app.include_router(web.router)
app.include_router(api.router)
app.include_router(admin.router)

app.add_event_handler("startup", seed_admin)
app.add_event_handler("startup", check_secret_key)
