import time

import pyotp
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    RegistrationCredential,
    UserVerificationRequirement,
)

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Passkey, User
from ..security import (
    create_session_token,
    hash_password,
    rate_limit,
    verify_password,
)
from ..ui import templates

router = APIRouter(prefix="/auth")

# In-memory pending WebAuthn challenges: {user_id: (challenge_b64, expires_at)}
_pending_challenges: dict[str, tuple[str, float]] = {}


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    totp_code: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not rate_limit(f"login:{email.lower()}", limit=10, window_seconds=300):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Terlalu banyak percobaan. Coba lagi nanti."}, status_code=429
        )
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", {"error": "Email atau password salah."})

    if user.totp_enabled:
        if not totp_code or not pyotp.TOTP(user.totp_secret).verify(totp_code):
            return templates.TemplateResponse(request, "login.html", {"error": "Kode 2FA salah."})

    token = create_session_token(user.id)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "session", token, max_age=settings.session_max_age, httponly=True,
        secure=settings.cookie_secure, samesite="strict",
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie("session")
    return response


# ---- Passkey registration (after login, on settings page) ----

@router.post("/passkey/register/options")
def passkey_register_options(request: Request, user: User = Depends(get_current_user)):
    options: PublicKeyCredentialCreationOptions = generate_registration_options(
        rp_id=settings.rp_id,
        rp_name=settings.app_name,
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED
        ),
    )
    _pending_challenges[user.id] = (bytes_to_base64url(options.challenge), time.monotonic() + 300)
    return {"options": options.model_dump(mode="json")}


@router.post("/passkey/register/verify")
def passkey_register_verify(
    credential: RegistrationCredential,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pending = _pending_challenges.pop(user.id, None)
    if not pending or pending[1] < time.monotonic():
        raise HTTPException(status_code=400, detail="No pending registration")
    expected_challenge = pending[0]

    verification = verify_registration_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(expected_challenge),
        expected_rp_id=settings.rp_id,
        expected_origin=settings.rp_origin,
    )
    db.add(Passkey(
        user_id=user.id,
        credential_id=bytes_to_base64url(verification.credential_id),
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
    ))
    db.commit()
    return {"ok": True}


@router.post("/passkey/register/delete")
def passkey_register_delete(
    credential_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    passkey = db.query(Passkey).filter(
        Passkey.credential_id == credential_id, Passkey.user_id == user.id
    ).first()
    if passkey:
        db.delete(passkey)
        db.commit()
    return RedirectResponse("/settings", status_code=303)
