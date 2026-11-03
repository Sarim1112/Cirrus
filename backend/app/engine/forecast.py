"""Project the daily balance forward and work out what's safe to spend."""

from datetime import date, timedelta
from math import sqrt
from statistics import pstdev

from .core import Txn, is_spending, month_end
from .recurring import Stream, detect_recurring

_Z80 = 1.28  # 80% band


def variable_daily_spend(
    txns: list[Txn], streams: list[Stream], today: date
) -> tuple[float, float]:
    """Mean and standard deviation of daily non-recurring spending over the last 90 days."""
    recurring_ids = {i for s in streams for i in s.txn_ids}
    start = today - timedelta(days=90)
    if txns:
        start = max(start, min(t.date for t in txns))
    days = max((today - start).days, 1)
    daily = [0] * days
    for txn in txns:
        offset = (txn.date - start).days
        if 0 <= offset < days and is_spending(txn) and txn.id not in recurring_ids:
            daily[offset] += -txn.amount_cents
    return sum(daily) / days, pstdev(daily) if days > 1 else 0.0


def build_forecast(
    txns: list[Txn],
    today: date,
    balance_cents: int | None,
    buffer_cents: int = 10_000,
    goal_monthly_cents: int = 0,
    horizon_days: int = 45,
    streams: list[Stream] | None = None,
) -> dict:
    streams = detect_recurring(txns, today) if streams is None else streams
    mean_daily, sd_daily = variable_daily_spend(txns, streams, today)
    end = today + timedelta(days=horizon_days)
    tomorrow = today + timedelta(days=1)

    events: dict[date, list[dict]] = {}
    for stream in streams:
        sign = -1 if stream.direction == "out" else 1
        for day in stream.dates_between(tomorrow, end):
            events.setdefault(day, []).append(
                {
                    "merchant": stream.merchant,
                    "category": stream.category,
                    "amount_cents": sign * stream.amount_cents,
                    "date": day.isoformat(),
                }
            )

    upcoming = sorted(
        (e for rows in events.values() for e in rows),
        key=lambda e: (e["date"], e["amount_cents"]),
    )
    income_days = sorted(
        d for d, rows in events.items() if any(e["amount_cents"] > 0 for e in rows)
    )
    window_end = income_days[0] if income_days and (income_days[0] - today).days <= 31 else None
    window_kind = "payday" if window_end else "month_end"
    if window_end is None:
        window_end = month_end(today) if today < month_end(today) else end

    latest = max((t.date for t in txns), default=None)
    result: dict = {
        "latest_data_date": latest.isoformat() if latest else None,
        "stale_days": max((today - latest).days, 0) if latest else 0,
        "needs_balance": balance_cents is None,
        "daily_variable_cents": round(mean_daily),
        "upcoming": upcoming,
        "window_end": window_end.isoformat(),
        "window_kind": window_kind,
        "points": [],
        "low_point": None,
        "month_end_balance_cents": None,
        "safe_to_spend": None,
    }
    if balance_cents is None:
        return result

    running = float(balance_cents)
    points = [
        {
            "date": today.isoformat(),
            "balance_cents": balance_cents,
            "low_cents": balance_cents,
            "high_cents": balance_cents,
        }
    ]
    for offset, day in enumerate(
        (today + timedelta(days=i) for i in range(1, horizon_days + 1)), start=1
    ):
        running -= mean_daily
        running += sum(e["amount_cents"] for e in events.get(day, []))
        band = _Z80 * sd_daily * sqrt(offset)
        points.append(
            {
                "date": day.isoformat(),
                "balance_cents": round(running),
                "low_cents": round(running - band),
                "high_cents": round(running + band),
            }
        )
    result["points"] = points
    low = min(points[1:], key=lambda p: p["balance_cents"], default=points[0])
    result["low_point"] = {"date": low["date"], "balance_cents": low["balance_cents"]}
    month_close = month_end(today).isoformat()
    closing = next((p for p in points if p["date"] == month_close), None)
    result["month_end_balance_cents"] = closing["balance_cents"] if closing else None

    # Safe to spend: what's left before the next pay after bills, a buffer and goal money.
    days_left = max((window_end - today).days, 1)
    bills = -sum(
        e["amount_cents"]
        for e in upcoming
        if e["amount_cents"] < 0 and date.fromisoformat(e["date"]) <= window_end
    )
    reserve = round(goal_monthly_cents * days_left / 30.44)
    simple = balance_cents - bills - buffer_cents - reserve

    # Spending everything before payday isn't safe if rent lands right after it. Walk the next
    # 31 days, assuming usual spending resumes after the window, and find the tightest day.
    tightest = simple
    horizon = today + timedelta(days=31)
    running_events = 0
    for day in sorted(events):
        if day > horizon:
            break
        running_events += sum(e["amount_cents"] for e in events[day])
        if day > window_end:
            later_spend = round(mean_daily * (day - window_end).days)
            tightest = min(
                tightest, balance_cents + running_events - later_spend - buffer_cents - reserve
            )
    held_back = simple - tightest
    available = tightest
    result["safe_to_spend"] = {
        "amount_cents": max(0, available),
        "shortfall_cents": max(0, -available),
        "per_day_cents": max(0, available) // days_left,
        "days": days_left,
        "until": window_end.isoformat(),
        "until_kind": window_kind,
        "usual_per_day_cents": round(mean_daily),
        "breakdown": {
            "balance_cents": balance_cents,
            "bills_cents": bills,
            "buffer_cents": buffer_cents,
            "goals_cents": reserve,
            "held_back_cents": held_back,
        },
    }
    return result
