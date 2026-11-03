"""Budgets built from the user's own history instead of a generic 50/30/20 rule."""

from dataclasses import asdict, dataclass
from datetime import date
from statistics import median, quantiles

from ..categories import FIXED, SPENDING_CATEGORIES
from .core import (
    Txn,
    complete_months_with_data,
    days_in_month,
    in_months,
    month_key,
    spending_cents,
)


def _round_up(cents: int, step: int = 500) -> int:
    return ((cents + step - 1) // step) * step


def _round_nearest(cents: int, step: int = 500) -> int:
    return round(cents / step) * step


def category_history(txns: list[Txn], today: date, months: int = 6) -> dict[str, list[int]]:
    """Monthly net spending per category for recent complete months. Zero months are included."""
    window = complete_months_with_data(txns, today, months)
    history: dict[str, list[int]] = {}
    for category in SPENDING_CATEGORIES:
        values = [
            max(0, spending_cents(t for t in in_months(txns, [m]) if t.category == category))
            for m in window
        ]
        if any(values):
            history[category] = values
    return history


@dataclass
class BudgetSuggestion:
    category: str
    limit_cents: int
    typical_cents: int
    lowest_cents: int
    highest_cents: int
    saving_cents: int
    kind: str  # "fixed", "flexible" or "occasional"
    reason: str


def suggest_budgets(txns: list[Txn], today: date, fmt) -> list[BudgetSuggestion]:
    """Fixed costs stay as they are. Flexible costs move toward the user's own better months.
    Occasional costs become a monthly set-aside."""
    suggestions = []
    for category, values in category_history(txns, today).items():
        typical = round(median(values))
        low, high = min(values), max(values)
        active_months = sum(1 for v in values if v > 0)

        if category in FIXED:
            limit = _round_up(max(typical, values[-1]))
            kind = "fixed"
            reason = f"This stays close to {fmt(typical)} a month, so it's set to cover the bill."
        elif active_months <= len(values) / 2:
            limit = _round_up(round(sum(values) / len(values)))
            kind = "occasional"
            reason = (
                f"You only spend on this some months, up to {fmt(high)}. "
                f"Setting aside {fmt(limit)} monthly smooths out those months."
            )
        else:
            better_month = quantiles(values, n=4)[0] if len(values) >= 3 else low
            # Aim between the typical month and a good month, and never more than 15% lower.
            target = max((typical + better_month) / 2, typical * 0.85)
            limit = min(_round_nearest(round(target)), _round_up(typical))
            kind = "flexible"
            if limit >= typical or better_month >= typical * 0.97:
                reason = f"This stays close to {fmt(typical)} a month, so the target matches it."
            else:
                reason = (
                    f"A typical month is {fmt(typical)} and your better months are near "
                    f"{fmt(round(better_month))}. This target is within reach."
                )
        limit = max(limit, 500)
        suggestions.append(
            BudgetSuggestion(
                category=category,
                limit_cents=limit,
                typical_cents=typical,
                lowest_cents=low,
                highest_cents=high,
                saving_cents=max(0, typical - limit),
                kind=kind,
                reason=reason,
            )
        )
    return sorted(suggestions, key=lambda s: -s.typical_cents)


def budget_status(txns: list[Txn], budgets: dict[str, int], today: date) -> list[dict]:
    """Where each budget stands this month and where it's likely to finish."""
    current = month_key(today)
    this_month = [t for t in txns if month_key(t.date) == current]
    history = category_history(txns, today)
    fraction_left = 1 - today.day / days_in_month(today)
    rows = []
    for category, limit in budgets.items():
        category_rows = [t for t in this_month if t.category == category]
        spent = max(0, spending_cents(category_rows))
        typical = round(median(history[category])) if category in history else None
        if category in FIXED:
            projected = max(spent, typical or spent)
        elif typical is not None:
            # Blend actual spending with the usual pace, which stays stable early in the month.
            projected = round(spent + typical * fraction_left)
        else:
            elapsed = max(today.day, 1) / days_in_month(today)
            projected = round(spent / elapsed)
        if spent > limit:
            status = "over"
        elif projected > limit * 1.05 and today.day >= 8:
            # Before the second week, a projection says more about history than about this month.
            status = "watch"
        else:
            status = "ok"
        rows.append(
            {
                "category": category,
                "limit_cents": limit,
                "spent_cents": spent,
                "remaining_cents": limit - spent,
                "projected_cents": projected,
                "percent_used": round(spent / limit * 100) if limit else 0,
                "status": status,
                "txn_ids": [t.id for t in category_rows],
            }
        )
    order = {"over": 0, "watch": 1, "ok": 2}
    return sorted(rows, key=lambda r: (order[r["status"]], -r["percent_used"]))


def savings_tips(txns: list[Txn], today: date, fmt) -> list[dict]:
    """The largest realistic savings, based only on categories the user can actually flex."""
    suggestions = [s for s in suggest_budgets(txns, today, fmt) if s.kind == "flexible"]
    window = complete_months_with_data(txns, today, 3)
    if not window:
        return []
    tips = []
    for suggestion in suggestions:
        rows = [t for t in in_months(txns, window) if t.category == suggestion.category]
        # The median month, so a single big purchase doesn't look like a habit worth trimming.
        recent = round(
            median(
                max(0, spending_cents(t for t in rows if month_key(t.date) == month))
                for month in window
            )
        )
        saving = recent - suggestion.limit_cents
        if saving < 500:
            continue
        merchants: dict[str, int] = {}
        for txn in rows:
            merchants[txn.merchant] = merchants.get(txn.merchant, 0) + (-txn.amount_cents)
        top = max(merchants, key=merchants.get) if merchants else None
        tips.append(
            {
                **asdict(suggestion),
                "recent_cents": recent,
                "saving_cents": saving,
                "top_merchant": top,
                "yearly_saving_cents": saving * 12,
                "txn_ids": [t.id for t in sorted(rows, key=lambda t: t.amount_cents)[:12]],
            }
        )
    return sorted(tips, key=lambda t: -t["saving_cents"])[:4]


def flexible_cut_options(txns: list[Txn], today: date) -> list[dict]:
    """Up to 25% of each flexible category, biggest first. Used when a plan has a gap."""
    window = complete_months_with_data(txns, today, 3)
    if not window:
        return []
    options = []
    for category in SPENDING_CATEGORIES:
        if category in FIXED:
            continue
        rows = [t for t in in_months(txns, window) if t.category == category]
        monthly = round(max(0, spending_cents(rows)) / len(window))
        if monthly >= 2000:
            options.append(
                {"category": category, "monthly_cents": monthly, "cut_cents": round(monthly * 0.25)}
            )
    return sorted(options, key=lambda o: -o["cut_cents"])
