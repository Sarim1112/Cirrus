"""Proactive findings: things worth telling the user before they ask."""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from ..categories import FIXED, NON_SPENDING, OTHER
from .budgets import budget_status
from .core import (
    Txn,
    complete_months_with_data,
    in_months,
    is_spending,
    month_key,
    spending_cents,
)
from .recurring import Stream

_LOOKBACK = 45
_DAILY_HABITS = {"Groceries", "Dining", "Transport", "Food Delivery"}


def _item(key, kind, severity, title, detail, impact=0, txn_ids=None, action=None):
    return {
        "key": key,
        "kind": kind,
        "severity": severity,  # alert, watch, info or good
        "title": title,
        "detail": detail,
        "monthly_impact_cents": impact,
        "txn_ids": txn_ids or [],
        "action": action,
    }


def unusual_transactions(txns: list[Txn], today: date, fmt) -> list[dict]:
    """Robust outlier test (median and MAD), so one huge purchase can't hide the next one."""
    start = today - timedelta(days=_LOOKBACK)
    history: dict[str, list[int]] = defaultdict(list)
    for txn in txns:
        if txn.amount_cents < 0 and is_spending(txn):
            history[txn.category].append(-txn.amount_cents)
    found = []
    for txn in txns:
        if txn.date < start or txn.amount_cents >= 0 or not is_spending(txn):
            continue
        if txn.category in FIXED:
            continue
        values = history[txn.category]
        if len(values) < 8:
            continue
        amount = -txn.amount_cents
        center = median(values)
        spread = median(abs(v - center) for v in values) or 1
        score = 0.6745 * (amount - center) / spread
        if score > 3.5 and amount >= center * 2 and amount - center >= 5000:
            found.append(
                _item(
                    f"unusual:{txn.id}",
                    "unusual",
                    "watch",
                    f"{fmt(amount)} at {txn.merchant} is unusual",
                    f"A typical {txn.category} purchase for you is about {fmt(round(center))}.",
                    txn_ids=[txn.id],
                    action="Check this charge is right",
                )
            )
    return sorted(found, key=lambda i: i["key"])[:5]


def duplicate_charges(txns: list[Txn], today: date, fmt) -> list[dict]:
    start = today - timedelta(days=_LOOKBACK)
    recent = sorted(
        (t for t in txns if t.date >= start and t.amount_cents < 0 and is_spending(t)),
        key=lambda t: (t.merchant, t.amount_cents, t.date),
    )
    found = []
    for a, b in zip(recent, recent[1:], strict=False):
        if (
            a.merchant == b.merchant
            and a.amount_cents == b.amount_cents
            and 0 <= (b.date - a.date).days <= 2
            and -a.amount_cents >= 1000
            and a.category not in _DAILY_HABITS
        ):
            found.append(
                _item(
                    f"duplicate:{a.id}",
                    "duplicate",
                    "alert",
                    f"Possible double charge from {a.merchant}",
                    f"Two charges of {fmt(-a.amount_cents)} landed within two days. "
                    "If you only bought once, ask them for a refund.",
                    txn_ids=[a.id, b.id],
                    action="Review both charges",
                )
            )
    return found


def price_increases(streams: list[Stream], today: date, fmt) -> list[dict]:
    found = []
    for stream in streams:
        if (
            stream.direction == "out"
            and stream.active
            and stream.price_change_cents > 0
            and stream.price_change_date
            and (today - stream.price_change_date).days <= 120
        ):
            monthly = round(stream.price_change_cents * 30.44 / stream.interval_days)
            found.append(
                _item(
                    f"price:{stream.merchant}:{stream.price_change_date.isoformat()}",
                    "price_increase",
                    "watch",
                    f"{stream.merchant} went up by {fmt(stream.price_change_cents)}",
                    f"It was {fmt(stream.previous_amount_cents or 0)} and is now "
                    f"{fmt(stream.amount_cents)}, which adds {fmt(monthly * 12)} a year.",
                    impact=monthly,
                    txn_ids=stream.txn_ids[-3:],
                    action="Decide if it's still worth it",
                )
            )
    return found


def subscription_review(streams: list[Stream], today: date, fmt) -> list[dict]:
    active = [s for s in streams if s.is_subscription and s.active]
    if not active:
        return []
    total = sum(s.monthly_cents for s in active)
    oldest = max(active, key=lambda s: (today - s.first_date).days)
    found = [
        _item(
            "subscriptions:total",
            "subscriptions",
            "info",
            f"{len(active)} subscriptions cost {fmt(total)} a month",
            f"That's {fmt(total * 12)} a year. {oldest.merchant} has been running the longest.",
            impact=total,
            txn_ids=[s.txn_ids[-1] for s in active],
            action="Review your subscriptions",
        )
    ]
    # Long-running, unchanging, smaller charges are the ones people tend to forget about.
    quiet = [
        s
        for s in active
        if (today - s.first_date).days >= 180
        and s.price_change_cents == 0
        and s.monthly_cents < 2500
    ]
    if quiet:
        pick = max(quiet, key=lambda s: s.monthly_cents)
        spent = pick.amount_cents * pick.occurrences
        found.append(
            _item(
                f"forgotten:{pick.merchant}",
                "forgotten",
                "watch",
                f"Still using {pick.merchant}?",
                f"It has charged {fmt(pick.amount_cents)} {pick.cadence} {pick.occurrences} times, "
                f"which adds up to {fmt(spent)}. Cancelling saves {fmt(pick.monthly_cents * 12)} "
                "a year.",
                impact=pick.monthly_cents,
                txn_ids=pick.txn_ids[-3:],
                action="Cancel it if you don't use it",
            )
        )
    return found


def _typical_month(rows: list[Txn], months: list[str]) -> int:
    """The median month, so one big purchase doesn't look like a lasting change."""
    return round(median(max(0, spending_cents(in_months(rows, [m]))) for m in months))


def category_shifts(txns: list[Txn], today: date, fmt) -> list[dict]:
    """Slow drift that no single transaction reveals: last 3 months against the 3 before."""
    window = complete_months_with_data(txns, today, 6)
    if len(window) < 6:
        return []
    earlier, later = window[:3], window[3:]
    categories = {
        t.category for t in txns if t.category not in NON_SPENDING and t.category != OTHER
    }
    found = []
    for category in sorted(categories):
        rows = [t for t in txns if t.category == category]
        active_earlier = len({month_key(t.date) for t in in_months(rows, earlier)})
        active_later = len({month_key(t.date) for t in in_months(rows, later)})
        if active_earlier < 2 or active_later < 2:
            continue
        before = _typical_month(rows, earlier)
        after = _typical_month(rows, later)
        change = after - before
        if before == 0:
            continue
        percent = round(change / before * 100)
        if category in FIXED:
            continue
        if change >= 2500 and percent >= 15:
            found.append(
                _item(
                    f"creep:{category}:{later[-1]}",
                    "creep",
                    "watch",
                    f"{category} has crept up {percent}%",
                    f"A typical month is now {fmt(after)}, up from {fmt(before)} three months "
                    f"earlier. That's {fmt(change * 12)} more a year.",
                    impact=change,
                    txn_ids=[
                        t.id
                        for t in sorted(in_months(rows, later), key=lambda t: t.amount_cents)[:12]
                    ],
                    action=f"Set a {category} budget",
                )
            )
        elif change <= -2500 and percent <= -15:
            found.append(
                _item(
                    f"win:{category}:{later[-1]}",
                    "win",
                    "good",
                    f"{category} is down {abs(percent)}%",
                    f"A typical month is now {fmt(after)}, down from {fmt(before)}. "
                    f"That frees up {fmt(-change * 12)} a year.",
                    impact=change,
                )
            )
    return found


def budget_alerts(txns: list[Txn], budgets: dict[str, int], today: date, fmt) -> list[dict]:
    found = []
    for row in budget_status(txns, budgets, today):
        if row["status"] == "over":
            found.append(
                _item(
                    f"budget-over:{row['category']}:{today:%Y-%m}",
                    "budget",
                    "alert",
                    f"{row['category']} is over budget",
                    f"You've spent {fmt(row['spent_cents'])} of {fmt(row['limit_cents'])} "
                    "this month.",
                    txn_ids=row["txn_ids"][:12],
                    action="See this month's spending",
                )
            )
        elif row["status"] == "watch":
            found.append(
                _item(
                    f"budget-watch:{row['category']}:{today:%Y-%m}",
                    "budget",
                    "watch",
                    f"{row['category']} is heading over budget",
                    f"You've spent {fmt(row['spent_cents'])} so far. At your usual pace you'll "
                    f"reach {fmt(row['projected_cents'])} against a {fmt(row['limit_cents'])} "
                    "budget.",
                    txn_ids=row["txn_ids"][:12],
                    action="Slow down in this category",
                )
            )
    return found


def forecast_alerts(forecast: dict | None, buffer_cents: int, fmt) -> list[dict]:
    if not forecast or not forecast.get("low_point"):
        return []
    low = forecast["low_point"]
    if low["balance_cents"] >= buffer_cents:
        return []
    day = date.fromisoformat(low["date"])
    severity = "alert" if low["balance_cents"] < 0 else "watch"
    return [
        _item(
            f"low-balance:{low['date']}",
            "low_balance",
            severity,
            f"Your balance may drop to {fmt(low['balance_cents'])}",
            f"That's the projected low on {day:%B} {day.day}, based on upcoming bills and your "
            "usual spending.",
            action="See your forecast",
        )
    ]


def goal_alerts(goal_plan: dict | None, today: date, fmt) -> list[dict]:
    found = []
    for plan in (goal_plan or {}).get("plans", []):
        if plan["status"] == "behind":
            found.append(
                _item(
                    f"goal:{plan['id']}:{today:%Y-%m}",
                    "goal",
                    "watch",
                    f"Your {plan['name']} goal needs attention",
                    f"It needs {fmt(plan['required_monthly_cents'])} a month, and your current "
                    f"surplus can cover {fmt(plan['allocated_monthly_cents'])}.",
                    action="See your goal plan",
                )
            )
    return found


_SEVERITY_ORDER = {"alert": 0, "watch": 1, "info": 2, "good": 3}
_KIND_ORDER = {
    "duplicate": 0,
    "low_balance": 0,
    "budget": 1,
    "unusual": 2,
    "goal": 2,
    "price_increase": 3,
    "creep": 3,
    "forgotten": 4,
    "subscriptions": 5,
    "win": 6,
}


def build_insights(
    txns: list[Txn],
    today: date,
    streams: list[Stream],
    budgets: dict[str, int],
    fmt,
    forecast: dict | None = None,
    goal_plan: dict | None = None,
    buffer_cents: int = 10_000,
    dismissed: set[str] | None = None,
) -> list[dict]:
    anchor = min(today, max((t.date for t in txns), default=today))
    items = [
        *duplicate_charges(txns, anchor, fmt),
        *forecast_alerts(forecast, buffer_cents, fmt),
        *budget_alerts(txns, budgets, today, fmt),
        *goal_alerts(goal_plan, today, fmt),
        *unusual_transactions(txns, anchor, fmt),
        *price_increases(streams, anchor, fmt),
        *category_shifts(txns, today, fmt),
        *subscription_review(streams, today, fmt),
    ]
    dismissed = dismissed or set()
    items = [i for i in items if i["key"] not in dismissed]
    return sorted(
        items,
        key=lambda i: (
            _SEVERITY_ORDER[i["severity"]],
            _KIND_ORDER[i["kind"]],
            -abs(i["monthly_impact_cents"]),
        ),
    )
