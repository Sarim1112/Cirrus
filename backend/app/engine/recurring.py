"""Detect subscriptions, bills and regular income from transaction history."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from ..categories import TRANSFERS
from .core import Txn, add_months

# name, expected gap in days, allowed drift
_CADENCES = (
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("monthly", 30.44, 5),
    ("quarterly", 91.3, 12),
    ("yearly", 365.25, 20),
)
# Everyday spending at the same shop isn't a bill unless the amount is near-identical.
_HABITUAL = {"Groceries", "Dining", "Food Delivery", "Shopping", "Transport", "Entertainment"}


@dataclass
class Stream:
    merchant: str
    category: str
    direction: str  # "out" or "in"
    cadence: str
    interval_days: float
    amount_cents: int  # latest charge, positive
    typical_cents: int
    monthly_cents: int
    first_date: date
    last_date: date
    next_date: date
    occurrences: int
    active: bool
    previous_amount_cents: int | None = None
    price_change_cents: int = 0
    price_change_date: date | None = None
    is_subscription: bool = False
    txn_ids: list[str] = field(default_factory=list)

    def dates_between(self, start: date, end: date) -> list[date]:
        """Expected dates in [start, end]. A slightly late charge is assumed to arrive at start."""
        if not self.active:
            return []
        current = self.next_date
        found = []
        if current < start:
            current_late = current
            while current < start:
                current = self._step(current)
            # The latest expected date hasn't shown up yet, so it's probably just pending.
            if (start - current_late).days <= 7 and start <= end:
                found.append(start)
        while current <= end:
            found.append(current)
            current = self._step(current)
        return found

    def _step(self, current: date) -> date:
        if self.cadence == "monthly":
            return add_months(current, 1, self.last_date.day)
        if self.cadence == "quarterly":
            return add_months(current, 3, self.last_date.day)
        if self.cadence == "yearly":
            return add_months(current, 12, self.last_date.day)
        return current + timedelta(days=round(self.interval_days))


def _classify_gaps(gaps: list[int]) -> tuple[str, float] | None:
    if not gaps:
        return None
    typical = median(gaps)
    for name, expected, drift in _CADENCES:
        if abs(typical - expected) <= drift:
            regular = sum(1 for gap in gaps if abs(gap - expected) <= drift * 1.5)
            if regular / len(gaps) >= 0.7:
                return name, expected
    return None


def _spread(values: list[int]) -> float:
    center = median(values)
    return median(abs(v - center) for v in values) / center if center else 1.0


def detect_recurring(txns: list[Txn], today: date) -> list[Stream]:
    grouped: dict[tuple[str, str], list[Txn]] = defaultdict(list)
    for txn in txns:
        if txn.category == TRANSFERS or txn.merchant == "Unknown merchant":
            continue
        direction = "out" if txn.amount_cents < 0 else "in"
        grouped[(txn.merchant, direction)].append(txn)

    # Measure from the newest data, so an old statement doesn't make every bill look cancelled
    # and quietly overstate what's safe to spend.
    latest_data = min(today, max((t.date for t in txns), default=today))
    streams: list[Stream] = []
    for (merchant, direction), rows in grouped.items():
        rows.sort(key=lambda t: t.date)
        amounts = [abs(t.amount_cents) for t in rows]
        gaps = [(b.date - a.date).days for a, b in zip(rows, rows[1:], strict=False)]
        cadence = _classify_gaps(gaps)
        if cadence is None:
            continue
        name, interval = cadence
        if len(rows) < (2 if name == "yearly" else 3):
            continue
        category = max({t.category for t in rows}, key=[t.category for t in rows].count)
        # Regular utility bills vary a lot, paycheques vary a little, habits vary freely.
        spread = _spread(amounts)
        if category in _HABITUAL and spread > 0.02:
            continue
        if spread > 0.35:
            continue

        latest = amounts[-1]
        typical = round(median(amounts))
        previous = amounts[-2] if len(amounts) >= 2 else None
        change, change_date = 0, None
        if name != "weekly" and category not in {"Utilities", "Income"}:
            # Walk back to the last time the amount actually changed.
            for earlier, later in zip(reversed(rows[:-1]), reversed(rows[1:]), strict=False):
                delta = abs(later.amount_cents) - abs(earlier.amount_cents)
                if delta:
                    change, change_date, previous = delta, later.date, abs(earlier.amount_cents)
                    break
        last = rows[-1].date
        if name == "monthly":
            next_date = add_months(last, 1)
        elif name == "quarterly":
            next_date = add_months(last, 3)
        elif name == "yearly":
            next_date = add_months(last, 12)
        else:
            next_date = last + timedelta(days=round(interval))
        streams.append(
            Stream(
                merchant=merchant,
                category=category,
                direction=direction,
                cadence=name,
                interval_days=interval,
                amount_cents=latest,
                typical_cents=typical,
                monthly_cents=round(latest * 30.44 / interval),
                first_date=rows[0].date,
                last_date=last,
                next_date=next_date,
                occurrences=len(rows),
                active=(latest_data - last).days <= interval * 1.75,
                previous_amount_cents=previous,
                price_change_cents=change,
                price_change_date=change_date,
                is_subscription=direction == "out" and category == "Subscriptions",
                txn_ids=[t.id for t in rows],
            )
        )
    return sorted(streams, key=lambda s: (s.direction, -s.monthly_cents, s.merchant))
