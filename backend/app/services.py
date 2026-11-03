"""Load a user's data into the analytics engine. Every query here is scoped by user_id."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import local_today
from .engine.context import FinanceContext
from .engine.core import Txn
from .engine.goals import GoalInput
from .models import Budget, DismissedInsight, Goal, Transaction, User


def load_txns(db: Session, user_id: str) -> list[Txn]:
    """Future-dated rows are left out, because analytics only reason about what has happened."""
    rows = db.execute(
        select(
            Transaction.id,
            Transaction.date,
            Transaction.amount_cents,
            Transaction.merchant,
            Transaction.category,
        )
        .where(Transaction.user_id == user_id, Transaction.date <= local_today())
        .order_by(Transaction.date)
    ).all()
    return [Txn(*row) for row in rows]


def load_context(db: Session, user: User) -> FinanceContext:
    today = local_today()
    txns = load_txns(db, user.id)
    budgets = {
        b.category: b.limit_cents
        for b in db.execute(select(Budget).where(Budget.user_id == user.id)).scalars()
    }
    goals = [
        GoalInput(g.id, g.name, g.target_cents, g.saved_cents, g.target_date)
        for g in db.execute(
            select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)
        ).scalars()
    ]
    dismissed = set(
        db.execute(
            select(DismissedInsight.key).where(DismissedInsight.user_id == user.id)
        ).scalars()
    )
    return FinanceContext(
        txns=txns,
        today=today,
        currency=user.currency,
        balance_cents=effective_balance(user, txns, today),
        buffer_cents=user.safety_buffer_cents,
        budgets=budgets,
        goals=goals,
        dismissed=dismissed,
    )


def effective_balance(user: User, txns: list[Txn], today) -> int | None:
    """Roll the last known balance forward using any transactions imported since that date."""
    if user.balance_cents is None:
        return None
    if user.balance_as_of is None:
        return user.balance_cents
    later = sum(t.amount_cents for t in txns if user.balance_as_of < t.date <= today)
    return user.balance_cents + later
