"""Settings, data export and permanent deletion."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import local_today
from ..db import get_db
from ..deps import current_user, enforce_limit
from ..models import Budget, ChatMessage, Goal, ImportBatch, Transaction, User
from ..schemas import DeleteAccountBody, SettingsBody
from ..security import SESSION_COOKIE, verify_password
from .auth import user_payload

router = APIRouter(prefix="/api/account", tags=["account"])


@router.patch("/settings")
def update_settings(
    body: SettingsBody, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.currency is not None:
        user.currency = body.currency
    if body.clear_balance:
        user.balance_cents, user.balance_as_of = None, None
    elif body.balance_cents is not None:
        user.balance_cents, user.balance_as_of = body.balance_cents, local_today()
    if body.safety_buffer_cents is not None:
        user.safety_buffer_cents = body.safety_buffer_cents
    db.commit()
    return user_payload(user)


@router.get("/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    enforce_limit(f"export:{user.id}", 10, 3600)

    def rows(model):
        return db.execute(select(model).where(model.user_id == user.id)).scalars().all()

    return {
        "account": user_payload(user),
        "transactions": [
            {"date": t.date.isoformat(), "amount_cents": t.amount_cents, "merchant": t.merchant,
             "category": t.category, "description": t.raw_description}
            for t in rows(Transaction)
        ],
        "budgets": [{"category": b.category, "limit_cents": b.limit_cents} for b in rows(Budget)],
        "goals": [
            {"name": g.name, "target_cents": g.target_cents, "saved_cents": g.saved_cents,
             "target_date": g.target_date.isoformat() if g.target_date else None}
            for g in rows(Goal)
        ],
        "imports": [
            {"filename": i.filename, "rows_imported": i.rows_imported,
             "created_at": i.created_at.isoformat()}
            for i in rows(ImportBatch)
        ],
        "chat": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in rows(ChatMessage)
        ],
    }  # fmt: skip


@router.post("/delete", status_code=204)
def delete_account(
    body: DeleteAccountBody,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Removes the user. Foreign keys cascade to every table holding their data."""
    enforce_limit(f"delete:{user.id}", 8, 300)
    if not user.is_demo and not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "That password isn't right, so nothing was deleted.")
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
