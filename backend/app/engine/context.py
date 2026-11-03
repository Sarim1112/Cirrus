"""Everything the analytics need for one user, computed once per request."""

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from .core import Txn
from .forecast import build_forecast
from .goals import GoalInput, plan_goals
from .insights import build_insights
from .recurring import Stream, detect_recurring

_SYMBOLS = {"CAD": "$", "USD": "$", "AUD": "$", "EUR": "€", "GBP": "£"}


def make_formatter(currency: str):
    symbol = _SYMBOLS.get(currency)

    def fmt(cents: int | float) -> str:
        cents = round(cents)
        sign = "-" if cents < 0 else ""
        value = abs(cents)
        number = f"{value // 100:,}" if value % 100 == 0 else f"{value / 100:,.2f}"
        return f"{sign}{symbol}{number}" if symbol else f"{sign}{currency} {number}"

    return fmt


@dataclass
class FinanceContext:
    txns: list[Txn]
    today: date
    currency: str = "CAD"
    balance_cents: int | None = None
    buffer_cents: int = 10_000
    budgets: dict[str, int] = field(default_factory=dict)
    goals: list[GoalInput] = field(default_factory=list)
    dismissed: set[str] = field(default_factory=set)

    @cached_property
    def fmt(self):
        return make_formatter(self.currency)

    @cached_property
    def streams(self) -> list[Stream]:
        return detect_recurring(self.txns, self.today)

    @cached_property
    def goal_plan(self) -> dict:
        return plan_goals(self.goals, self.txns, self.today)

    @cached_property
    def forecast(self) -> dict:
        return build_forecast(
            self.txns,
            self.today,
            self.balance_cents,
            self.buffer_cents,
            self.goal_plan["committed_monthly_cents"],
            streams=self.streams,
        )

    @cached_property
    def insights(self) -> list[dict]:
        return build_insights(
            self.txns,
            self.today,
            self.streams,
            self.budgets,
            self.fmt,
            forecast=self.forecast,
            goal_plan=self.goal_plan,
            buffer_cents=self.buffer_cents,
            dismissed=self.dismissed,
        )
