"""What-if scenarios and affordability checks."""

from datetime import date

from .budgets import flexible_cut_options
from .core import (
    Txn,
    add_months,
    average_monthly,
    complete_months_with_data,
    in_months,
    spending_cents,
)
from .recurring import Stream, detect_recurring


def _category_monthly(txns: list[Txn], today: date, category: str) -> int:
    window = complete_months_with_data(txns, today, 3)
    if not window:
        return 0
    rows = [t for t in in_months(txns, window) if t.category == category]
    return round(max(0, spending_cents(rows)) / len(window))


def _merchant_monthly(txns: list[Txn], today: date, merchant: str, streams: list[Stream]) -> int:
    for stream in streams:
        if (
            stream.merchant.lower() == merchant.lower()
            and stream.direction == "out"
            and stream.active
        ):
            return stream.monthly_cents
    window = complete_months_with_data(txns, today, 3)
    if not window:
        return 0
    rows = [t for t in in_months(txns, window) if t.merchant.lower() == merchant.lower()]
    return round(max(0, spending_cents(rows)) / len(window))


def simulate(
    txns: list[Txn],
    today: date,
    changes: list[dict],
    balance_cents: int | None = None,
    months: int = 12,
) -> dict:
    """Changes: cut_category{category,percent}, cancel_merchant{merchant,percent?},
    one_off{amount_cents,label,month_offset?}, income_change{monthly_cents},
    add_recurring{monthly_cents,label}."""
    streams = detect_recurring(txns, today)
    baseline = average_monthly(txns, today, 3)
    impacts, one_offs = [], []
    monthly_delta = 0
    warnings = []

    for change in changes:
        kind = change.get("type")
        if kind == "cut_category":
            base = _category_monthly(txns, today, change["category"])
            saved = round(base * change["percent"] / 100)
            monthly_delta += saved
            impacts.append(
                {
                    "label": f"Cut {change['category']} by {change['percent']:g}%",
                    "monthly_cents": saved,
                    "base_monthly_cents": base,
                }
            )
            if not base:
                warnings.append(f"You have no recent spending in {change['category']}.")
        elif kind == "cancel_merchant":
            base = _merchant_monthly(txns, today, change["merchant"], streams)
            percent = change.get("percent", 100)
            saved = round(base * percent / 100)
            monthly_delta += saved
            verb = "Cancel" if percent == 100 else f"Cut {percent:g}% of"
            impacts.append(
                {
                    "label": f"{verb} {change['merchant']}",
                    "monthly_cents": saved,
                    "base_monthly_cents": base,
                }
            )
            if not base:
                warnings.append(f"You have no recent spending at {change['merchant']}.")
        elif kind == "income_change":
            monthly_delta += change["monthly_cents"]
            impacts.append(
                {
                    "label": "Change in income",
                    "monthly_cents": change["monthly_cents"],
                    "base_monthly_cents": baseline["income_cents"],
                }
            )
        elif kind == "add_recurring":
            monthly_delta -= change["monthly_cents"]
            impacts.append(
                {
                    "label": change.get("label", "New monthly cost"),
                    "monthly_cents": -change["monthly_cents"],
                    "base_monthly_cents": 0,
                }
            )
        elif kind == "one_off":
            one_offs.append(change)
            impacts.append(
                {
                    "label": change.get("label", "One-off cost"),
                    "monthly_cents": 0,
                    "one_off_cents": -change["amount_cents"],
                    "base_monthly_cents": 0,
                }
            )

    start = balance_cents or 0
    series = []
    base_balance, new_balance = start, start
    for offset in range(months + 1):
        if offset:
            base_balance += baseline["net_cents"]
            new_balance += baseline["net_cents"] + monthly_delta
        for item in one_offs:
            if item.get("month_offset", 1) == offset:
                new_balance -= item["amount_cents"]
        series.append(
            {
                "month": add_months(today, offset).strftime("%Y-%m"),
                "baseline_cents": base_balance,
                "scenario_cents": new_balance,
            }
        )
    return {
        "baseline": baseline,
        "scenario": {
            "income_cents": baseline["income_cents"],
            "spending_cents": baseline["spending_cents"],
            "net_cents": baseline["net_cents"] + monthly_delta,
        },
        "monthly_delta_cents": monthly_delta,
        "yearly_delta_cents": monthly_delta * 12,
        "impacts": impacts,
        "series": series,
        "warnings": warnings,
        "has_balance": balance_cents is not None,
    }


def months_between(today: date, target: date) -> int:
    """Whole months available, at least one. Counting pay cycles rather than calendar days."""
    months = (target.year - today.year) * 12 + target.month - today.month
    return max(months, 1)


def afford(
    txns: list[Txn],
    today: date,
    amount_cents: int,
    by: date | None,
    balance_cents: int | None,
    buffer_cents: int = 10_000,
    committed_monthly_cents: int = 0,
    label: str = "this",
) -> dict:
    """Can the user pay for something by a date, and what would it take if not?

    The answer never relies on emptying the account: it leaves one month of spending untouched.
    """
    target = by or add_months(today, 3)
    months = months_between(today, target)
    average = average_monthly(txns, today, 3)
    surplus = average["net_cents"] - committed_monthly_cents
    from_surplus = max(0, surplus) * months
    cushion = average["spending_cents"] + buffer_cents
    spare_balance = max(0, (balance_cents or 0) - cushion)
    required_monthly = -(-amount_cents // months)
    gap_total = max(0, amount_cents - from_surplus - spare_balance)
    gap_monthly = -(-gap_total // months)

    cuts, covered = [], 0
    if gap_monthly:
        for option in flexible_cut_options(txns, today):
            if covered >= gap_monthly:
                break
            take = min(option["cut_cents"], gap_monthly - covered)
            cuts.append({**option, "cut_cents": take})
            covered += take

    if amount_cents <= from_surplus:
        verdict = "yes"
    elif amount_cents <= from_surplus + spare_balance:
        verdict = "yes_with_savings"
    elif covered >= gap_monthly:
        verdict = "with_cuts"
    else:
        verdict = "not_yet"

    earliest = None
    if verdict == "not_yet":
        monthly_capacity = max(0, surplus) + covered
        if monthly_capacity > 0:
            need = max(0, amount_cents - spare_balance)
            wait = -(-need // monthly_capacity)
            earliest = add_months(today, wait)

    return {
        "label": label,
        "amount_cents": amount_cents,
        "by": target.isoformat(),
        "months": months,
        "verdict": verdict,
        "monthly_surplus_cents": surplus,
        "committed_monthly_cents": committed_monthly_cents,
        "surplus_by_date_cents": from_surplus,
        "spare_balance_cents": spare_balance,
        "cushion_cents": cushion,
        "required_monthly_cents": required_monthly,
        "gap_cents": gap_total,
        "gap_monthly_cents": gap_monthly,
        "suggested_cuts": cuts,
        "earliest_date": earliest.isoformat() if earliest else None,
        "has_balance": balance_cents is not None,
    }
