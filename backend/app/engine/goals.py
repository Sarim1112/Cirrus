"""Savings plans that re-balance whenever spending changes."""

from dataclasses import dataclass
from datetime import date

from .budgets import flexible_cut_options
from .core import Txn, add_months, average_monthly
from .simulate import months_between


@dataclass
class GoalInput:
    id: str
    name: str
    target_cents: int
    saved_cents: int
    target_date: date | None


def plan_goals(goals: list[GoalInput], txns: list[Txn], today: date) -> dict:
    """Allocate the user's real monthly surplus to goals, earliest deadline first."""
    average = average_monthly(txns, today, 3)
    surplus = max(0, average["net_cents"])
    remaining_capacity = surplus
    committed = 0  # Only deadlines commit money. Open-ended goals take what's spare.
    plans = {}

    ordered = sorted(goals, key=lambda g: (g.target_date is None, g.target_date or date.max))
    for goal in ordered:
        remaining = max(0, goal.target_cents - goal.saved_cents)
        progress = round(goal.saved_cents / goal.target_cents * 100) if goal.target_cents else 0
        months = months_between(today, goal.target_date) if goal.target_date else None
        required = -(-remaining // months) if months else 0

        if remaining == 0:
            status, allocated, projected = "done", 0, today
        elif goal.target_date is None:
            allocated = remaining_capacity
            status = "open" if allocated else "paused"
            wait = -(-remaining // allocated) if allocated else None
            projected = add_months(today, wait) if wait else None
        else:
            allocated = min(required, remaining_capacity)
            if allocated >= required:
                status = "on_track"
            elif allocated >= required * 0.7:
                status = "tight"
            else:
                status = "behind"
            wait = -(-remaining // allocated) if allocated else None
            projected = add_months(today, wait) if wait else None
        remaining_capacity -= allocated
        if goal.target_date is not None:
            committed += allocated
        plans[goal.id] = {
            "id": goal.id,
            "name": goal.name,
            "target_cents": goal.target_cents,
            "saved_cents": goal.saved_cents,
            "remaining_cents": remaining,
            "percent": min(progress, 100),
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "months_left": months,
            "required_monthly_cents": required,
            "allocated_monthly_cents": allocated,
            "projected_date": projected.isoformat() if projected else None,
            "status": status,
            "cuts": [],
        }

    # For goals that fall short, show exactly which categories could close the gap.
    for plan in plans.values():
        gap = plan["required_monthly_cents"] - plan["allocated_monthly_cents"]
        if plan["status"] in {"tight", "behind"} and gap > 0:
            covered, cuts = 0, []
            for option in flexible_cut_options(txns, today):
                if covered >= gap:
                    break
                take = min(option["cut_cents"], gap - covered)
                cuts.append({**option, "cut_cents": take})
                covered += take
            plan["cuts"] = cuts
            plan["gap_monthly_cents"] = gap

    return {
        "monthly_surplus_cents": surplus,
        "unallocated_monthly_cents": surplus - committed,
        "committed_monthly_cents": committed,
        "average": average,
        "plans": [plans[g.id] for g in goals],
    }
