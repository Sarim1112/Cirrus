"""Accounts, sessions, password reset and the no-signup demo."""

import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings, local_today
from ..db import get_db, new_id, utcnow
from ..demo_data import DEMO_BALANCE_CENTS, DEMO_GOALS, build_rows
from ..deps import client_ip, current_user, enforce_limit, start_session
from ..engine.budgets import suggest_budgets
from ..engine.context import make_formatter
from ..engine.core import add_months
from ..ingest.parsers import ParseResult
from ..ingest.pipeline import commit_import
from ..models import AuthSession, Budget, Goal, PasswordReset, User
from ..schemas import ChangePasswordBody, ForgotBody, LoginBody, RegisterBody, ResetBody
from ..security import SESSION_COOKIE, hash_password, hash_token, new_token, verify_password
from ..services import load_txns

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("cirrus.auth")


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": None if user.is_demo else user.email,
        "display_name": user.display_name,
        "currency": user.currency,
        "balance_cents": user.balance_cents,
        "balance_as_of": user.balance_as_of.isoformat() if user.balance_as_of else None,
        "safety_buffer_cents": user.safety_buffer_cents,
        "is_demo": user.is_demo,
        "expires_at": user.expires_at.isoformat() + "Z" if user.expires_at else None,
    }


def _session_lifetime() -> timedelta:
    return timedelta(days=get_settings().session_days)


@router.post("/register", status_code=201)
def register(
    body: RegisterBody, request: Request, response: Response, db: Session = Depends(get_db)
):
    enforce_limit(f"register:{client_ip(request)}", 10, 3600)
    email = body.email.lower()
    local_part = email.split("@")[0]
    if len(local_part) >= 3 and local_part in body.password.lower():
        raise HTTPException(422, "Choose a password that doesn't contain your email.")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "An account with this email already exists. Sign in instead."
        ) from None
    start_session(db, user, response, _session_lifetime())
    return user_payload(user)


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    enforce_limit(f"login-ip:{client_ip(request)}", 30, 300)
    enforce_limit(f"login-email:{email}", 8, 300)
    user = db.execute(
        select(User).where(User.email == email, User.is_demo.is_(False))
    ).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That email and password don't match.")
    start_session(db, user, response, _session_lifetime())
    return user_payload(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_payload(user)


def _send_reset_email(to: str, link: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        if settings.is_production:
            log.error("Password reset requested, but SMTP isn't configured.")
        else:
            log.warning("SMTP isn't configured. Development reset link: %s", link)
        return
    message = EmailMessage()
    message["Subject"] = "Reset your Cirrus password"
    message["From"] = settings.smtp_from
    message["To"] = to
    message.set_content(
        f"Use this link to choose a new password. It expires in one hour.\n\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except OSError:
        log.exception("Couldn't send the password reset email")


@router.post("/forgot-password", status_code=202)
def forgot_password(
    body: ForgotBody, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Always answers the same way, so this can't be used to discover who has an account."""
    email = body.email.lower()
    enforce_limit(f"forgot-ip:{client_ip(request)}", 10, 3600)
    enforce_limit(f"forgot-email:{email}", 3, 3600)
    user = db.execute(
        select(User).where(User.email == email, User.is_demo.is_(False))
    ).scalar_one_or_none()
    if user:
        token = new_token()
        db.add(PasswordReset(user_id=user.id, token_hash=hash_token(token),
                             expires_at=utcnow() + timedelta(hours=1)))  # fmt: skip
        db.commit()
        link = f"{get_settings().public_url.rstrip('/')}/reset-password?token={token}"
        tasks.add_task(_send_reset_email, user.email, link)
    return {"message": "If that email has an account, a reset link is on its way."}


@router.post("/reset-password")
def reset_password(body: ResetBody, request: Request, db: Session = Depends(get_db)):
    enforce_limit(f"reset:{client_ip(request)}", 20, 3600)
    reset = db.execute(
        select(PasswordReset).where(
            PasswordReset.token_hash == hash_token(body.token),
            PasswordReset.used_at.is_(None),
            PasswordReset.expires_at > utcnow(),
        )
    ).scalar_one_or_none()
    if reset is None:
        raise HTTPException(
            400, "This reset link has expired or was already used. Request a new one."
        )
    user = db.get(User, reset.user_id)
    user.password_hash = hash_password(body.password)
    reset.used_at = utcnow()
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    return {"message": "Password changed. Sign in with your new password."}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.is_demo:
        raise HTTPException(403, "The demo doesn't have a password.")
    enforce_limit(f"change-password:{user.id}", 8, 300)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(401, "Your current password isn't right.")
    user.password_hash = hash_password(body.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    start_session(db, user, response, _session_lifetime())
    return {"message": "Password changed. Other devices have been signed out."}


def seed_demo_user(db: Session, today=None) -> User:
    """Create a throwaway user, and feed the sample statement through the real import pipeline."""
    settings = get_settings()
    today = today or local_today()
    user = User(
        email=f"demo-{new_id()}@demo.invalid",
        password_hash=None,
        display_name="Maya",
        currency="CAD",
        balance_cents=DEMO_BALANCE_CENTS,
        balance_as_of=today,
        is_demo=True,
        expires_at=utcnow() + timedelta(hours=settings.demo_ttl_hours),
    )
    db.add(user)
    db.flush()
    rows = build_rows(today)
    parsed = ParseResult(source_type="csv", rows=rows, total_rows=len(rows))
    commit_import(db, user, "sample-statement.csv", parsed)
    for name, target, saved, months in DEMO_GOALS:
        db.add(Goal(user_id=user.id, name=name, target_cents=target, saved_cents=saved,
                    target_date=add_months(today, months)))  # fmt: skip
    txns = load_txns(db, user.id)
    fmt = make_formatter(user.currency)
    wanted = {"Groceries", "Dining", "Food Delivery", "Shopping", "Entertainment", "Subscriptions"}
    for suggestion in suggest_budgets(txns, today, fmt):
        if suggestion.category in wanted:
            db.add(
                Budget(
                    user_id=user.id,
                    category=suggestion.category,
                    limit_cents=suggestion.limit_cents,
                )
            )
    db.commit()
    return user


@router.post("/demo", status_code=201)
def start_demo(request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.demo_enabled:
        raise HTTPException(404, "The demo isn't available here.")
    enforce_limit(f"demo:{client_ip(request)}", 10, 3600)
    user = seed_demo_user(db)
    start_session(db, user, response, timedelta(hours=settings.demo_ttl_hours))
    return user_payload(user)
