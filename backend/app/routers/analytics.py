"""Dashboard, forecast, insights, budgets, goals and what-if endpoints."""

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..engine import budgets as budget_engine
from ..engine.core import (
    add_months,
    average_monthly,
    by_category,
    by_merchant,
    in_months,
    month_key,
    monthly_series,
    totals,
)
from ..engine.recurring import Stream
from ..engine.simulate import afford, simulate
from ..models import Budget, DismissedInsight, Goal, User
from ..schemas import AffordBody, BudgetsBody, GoalBody, GoalUpdate, SimulateBody
from ..services import load_context

router = APIRouter(prefix="/api", tags=["analytics"])


def _stream(stream: Stream) -> dict:
    row = asdict(stream)
    for key in ("first_date", "last_date", "next_date", "price_change_date"):
        row[key] = row[key].isoformat() if row[key] else None
    row["recent_txn_ids"] = row.pop("txn_ids")[-6:]
    return row


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = load_context(db, user)
    current = month_key(ctx.today)
    previous = month_key(add_months(ctx.today.replace(day=1), -1))
    this_month = in_months(ctx.txns, [current])
    last_month = in_months(ctx.txns, [previous])
    return {
        "today": ctx.today.isoformat(),
        "has_data": bool(ctx.txns),
        "balance_cents": ctx.balance_cents,
        "this_month": totals(this_month),
        "last_month": totals(last_month),
        "average": average_monthly(ctx.txns, ctx.today, 3),
        "series": monthly_series(ctx.txns, ctx.today, 12),
        "categories": by_category(this_month)[:10],
        "last_month_categories": by_category(last_month)[:10],
        "top_merchants": by_merchant(this_month)[:6],
        "forecast": ctx.forecast,
        "insights": ctx.insights[:6],
        "budgets": [
            {k: v for k, v in r.items() if k != "txn_ids"}
            for r in budget_engine.budget_status(ctx.txns, ctx.budgets, ctx.today)
        ][:6],
    }


@router.get("/forecast")
def forecast(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return load_context(db, user).forecast


@router.get("/recurring")
def recurring(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = load_context(db, user)
    streams = [_stream(s) for s in ctx.streams]
    active_out = [s for s in ctx.streams if s.direction == "out" and s.active]
    return {
        "streams": streams,
        "subscriptions_monthly_cents": sum(
            s.monthly_cents for s in active_out if s.is_subscription
        ),
        "bills_monthly_cents": sum(s.monthly_cents for s in active_out if not s.is_subscription),
    }


@router.get("/insights")
def insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"insights": load_context(db, user).insights}


@router.post("/insights/{key:path}/dismiss", status_code=204)
def dismiss_insight(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(key) > 160:
        raise HTTPException(422, "That insight key is too long.")
    exists = db.execute(
        select(DismissedInsight).where(
            DismissedInsight.user_id == user.id, DismissedInsight.key == key
        )
    ).scalar_one_or_none()
    if not exists:
        db.add(DismissedInsight(user_id=user.id, key=key))
        db.commit()


@router.post("/simulate")
def run_simulation(
    body: SimulateBody, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    ctx = load_context(db, user)
    changes = [c.model_dump(exclude_none=True) for c in body.changes]
    for change in changes:
        required = {
            "cut_category": ("category", "percent"),
            "cancel_merchant": ("merchant",),
            "income_change": ("monthly_cents",),
            "add_recurring": ("monthly_cents",),
            "one_off": ("amount_cents",),
        }[change["type"]]
        if any(field not in change for field in required):
            raise HTTPException(422, f"{change['type']} needs: {', '.join(required)}.")
    return simulate(ctx.txns, ctx.today, changes, ctx.balance_cents)


@router.post("/afford")
def check_afford(
    body: AffordBody, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    ctx = load_context(db, user)
    return afford(
        ctx.txns,
        ctx.today,
        body.amount_cents,
        body.by,
        ctx.balance_cents,
        ctx.buffer_cents,
        ctx.goal_plan["committed_monthly_cents"],
        body.label,
    )


# ---------------------------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------------------------


@router.get("/budgets")
def budgets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = load_context(db, user)
    return {
        "status": budget_engine.budget_status(ctx.txns, ctx.budgets, ctx.today),
        "suggestions": [
            asdict(s) for s in budget_engine.suggest_budgets(ctx.txns, ctx.today, ctx.fmt)
        ],
        "history": budget_engine.category_history(ctx.txns, ctx.today),
    }


@router.put("/budgets")
def save_budgets(
    body: BudgetsBody, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Replace the whole set, which keeps the client and server trivially in sync."""
    db.execute(delete(Budget).where(Budget.user_id == user.id))
    seen = {}
    for item in body.budgets:
        seen[item.category] = item.limit_cents
    for category, limit in seen.items():
        db.add(Budget(user_id=user.id, category=category, limit_cents=limit))
    db.commit()
    return {"saved": len(seen)}


# ---------------------------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------------------------


@router.get("/goals")
def goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return load_context(db, user).goal_plan


def _owned_goal(db: Session, user: User, goal_id: str) -> Goal:
    goal = db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
    ).scalar_one_or_none()
    if goal is None:
        raise HTTPException(404, "That goal doesn't exist.")
    return goal


def _check_date(value: date | None, today: date) -> None:
    if value and value <= today:
        raise HTTPException(422, "Choose a target date in the future.")


@router.post("/goals", status_code=201)
def create_goal(body: GoalBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check_date(body.target_date, load_context(db, user).today)
    goal = Goal(user_id=user.id, **body.model_dump())
    db.add(goal)
    db.commit()
    return {"id": goal.id}


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: str,
    body: GoalUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goal = _owned_goal(db, user, goal_id)
    values = body.model_dump(exclude_unset=True, exclude={"clear_date"})
    if "target_date" in values:
        _check_date(values["target_date"], load_context(db, user).today)
    for key, value in values.items():
        if value is not None:
            setattr(goal, key, value)
    if body.clear_date:
        goal.target_date = None
    db.commit()
    return {"id": goal.id}


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_owned_goal(db, user, goal_id))
    db.commit()
