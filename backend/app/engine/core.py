"""Shared types and period helpers."""

import calendar
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from ..categories import INCOME, NON_SPENDING


@dataclass(frozen=True, slots=True)
class Txn:
    id: str
    date: date
    amount_cents: int
    merchant: str
    category: str


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_start(day: date) -> date:
    return day.replace(day=1)


def days_in_month(day: date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


def month_end(day: date) -> date:
    return day.replace(day=days_in_month(day))


def add_months(day: date, months: int, anchor_day: int | None = None) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = index // 12, index % 12 + 1
    wanted = anchor_day or day.day
    return date(year, month, min(wanted, calendar.monthrange(year, month)[1]))


def previous_months(today: date, count: int) -> list[str]:
    """The `count` complete months before today's month, oldest first."""
    first = month_start(today)
    return [month_key(add_months(first, -i)) for i in range(count, 0, -1)]


def complete_months_with_data(txns: Iterable[Txn], today: date, count: int) -> list[str]:
    """Up to `count` complete months inside the span of the user's data, oldest first.

    The window ends where the data ends. A statement from months ago still gives sensible
    averages, and its last month counts only if the statement reaches that month's final days.
    """
    txns = list(txns)
    if not txns:
        return []
    earliest = month_key(min(t.date for t in txns))
    latest = max(t.date for t in txns)
    end = month_start(today)
    if latest < end:
        reaches_month_end = latest.day >= days_in_month(latest) - 5
        end = add_months(month_start(latest), 1) if reaches_month_end else month_start(latest)
    window = [month_key(add_months(end, -i)) for i in range(count, 0, -1)]
    return [m for m in window if m >= earliest]


def is_spending(txn: Txn) -> bool:
    return txn.category not in NON_SPENDING


def in_months(txns: Iterable[Txn], months: Iterable[str]) -> list[Txn]:
    wanted = set(months)
    return [t for t in txns if month_key(t.date) in wanted]


def in_range(txns: Iterable[Txn], start: date, end: date) -> list[Txn]:
    return [t for t in txns if start <= t.date <= end]


def spending_cents(txns: Iterable[Txn]) -> int:
    """Net spending as a positive number. Refunds reduce the total."""
    return -sum(t.amount_cents for t in txns if is_spending(t))


def income_cents(txns: Iterable[Txn]) -> int:
    return sum(t.amount_cents for t in txns if t.category == INCOME)


def totals(txns: Iterable[Txn]) -> dict[str, int]:
    txns = list(txns)
    income, spending = income_cents(txns), spending_cents(txns)
    return {"income_cents": income, "spending_cents": spending, "net_cents": income - spending}


def group_spending(txns: Iterable[Txn], key) -> list[dict]:
    groups: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for txn in txns:
        if is_spending(txn):
            name = key(txn)
            groups[name] += -txn.amount_cents
            counts[name] += 1
    rows = [
        {"name": name, "amount_cents": cents, "count": counts[name]}
        for name, cents in groups.items()
        if cents > 0
    ]
    return sorted(rows, key=lambda r: (-r["amount_cents"], r["name"]))


def by_category(txns: Iterable[Txn]) -> list[dict]:
    return group_spending(txns, lambda t: t.category)


def by_merchant(txns: Iterable[Txn]) -> list[dict]:
    return group_spending(txns, lambda t: t.merchant)


def monthly_series(txns: Iterable[Txn], today: date, count: int = 12) -> list[dict]:
    """Income, spending and net for up to `count` months ending with the current month."""
    txns = list(txns)
    if not txns:
        return []
    earliest = month_start(min(t.date for t in txns))
    series = []
    for offset in range(count - 1, -1, -1):
        start = add_months(month_start(today), -offset)
        if start < earliest:
            continue
        key = month_key(start)
        series.append({"month": key, **totals(t for t in txns if month_key(t.date) == key)})
    return series


def average_monthly(txns: list[Txn], today: date, months: int = 3) -> dict[str, int]:
    """Average income, spending and net across recent complete months."""
    window = complete_months_with_data(txns, today, months)
    if not window:
        # Fewer than one complete month: scale what exists to a 30-day month.
        if not txns:
            return {"income_cents": 0, "spending_cents": 0, "net_cents": 0, "months": 0}
        span = max((today - min(t.date for t in txns)).days + 1, 14)
        base = totals(txns)
        scale = 30.44 / span
        income = round(base["income_cents"] * scale)
        spending = round(base["spending_cents"] * scale)
        return {
            "income_cents": income,
            "spending_cents": spending,
            "net_cents": income - spending,
            "months": 0,
        }
    base = totals(in_months(txns, window))
    size = len(window)
    income, spending = round(base["income_cents"] / size), round(base["spending_cents"] / size)
    return {
        "income_cents": income,
        "spending_cents": spending,
        "net_cents": income - spending,
        "months": size,
    }


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
