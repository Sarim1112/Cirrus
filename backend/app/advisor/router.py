"""Map a question to calculation tools with plain rules, before any model gets involved.

A small local model can lose the thread across several tool calls, so the common questions never
depend on it. Anything this router can't place falls through to the model, if one is running.
"""

import re

from ..engine.context import FinanceContext
from . import tools
from .parse import (
    find_category,
    find_merchant,
    parse_future_date,
    parse_money,
    parse_percent,
    parse_period,
)
from .tools import ToolOutput

_WHAT_IF = re.compile(
    r"\b(what if|what happens if|suppose|if i (were to |)(cut|cancel\w*|stop\w*|halve|reduce|drop\w*|quit|"
    r"spend less|got|get|earn|made|make|lost)|how much (would|could|will) i save)\b",
    re.I,
)
_AFFORD = re.compile(r"\b(afford|save up for|enough (money )?for|pay for)\b", re.I)
_GOALS = re.compile(r"\b(goals?|on track|saving for|savings plan)\b", re.I)
_FORECAST = re.compile(
    r"\b(safe to spend|how much (can|should) i spend|left to spend|forecast|month[- ]end|"
    r"end of (the |this )?month|run out|running out|my balance|payday|before i get paid|"
    r"how long will my money|daily limit|can i spend)\b",
    re.I,
)
_RECURRING = re.compile(
    r"\b(subscriptions?|recurring|regular (bills|payments)|bills?|memberships?)\b", re.I
)
_INSIGHTS = re.compile(
    r"\b(unusual|weird|strange|odd|suspicious|anomal\w*|alerts?|insights?|duplicate|double[- ]?charg\w*|"
    r"anything (wrong|i should know)|what should i know|price (increase|hike|rise)s?|went up|"
    r"creep\w*|changed)\b",
    re.I,
)
_TIPS = re.compile(
    r"\b(tips?|advice|advise|save more|saving money|save money|cut back|cut down|cut costs|spend less|"
    r"reduce (my )?spending|where can i (save|cut)|how (can|do|could|should) i save|overspend\w*|"
    r"help me (save|budget)|too much)\b",
    re.I,
)
_BUDGET_MAKE = re.compile(
    r"\b(suggest|create|make|build|set( up)?|recommend|design|plan)\b.{0,25}\bbudgets?\b|"
    r"\bwhat should my budget\b|\bbudget (for me|plan|suggestion)s?\b",
    re.I,
)
_BUDGET = re.compile(r"\bbudgets?\b", re.I)
_INCOME = re.compile(
    r"\b(income|salary|paycheck|paycheque|how much do i (make|earn)|earnings)\b", re.I
)
_TOP = re.compile(
    r"\b(top (merchants?|stores?|places?)|biggest (merchants?|expenses?|purchases?)|"
    r"where (do|did) i spend (the )?most|spend the most|most money)\b",
    re.I,
)
_SPENDING = re.compile(
    r"\b(how much|spend|spent|spending|expenses?|cost|costs|paid|pay|where did|where does|"
    r"compare|compared|breakdown|break down)\b",
    re.I,
)
_OVERVIEW = re.compile(
    r"\b(summary|summari[sz]e|overview|how am i doing|how'?s my|how is my|snapshot|recap|"
    r"financial (health|situation))\b",
    re.I,
)


def _parse_changes(message: str, ctx: FinanceContext) -> list[dict]:
    merchants = {t.merchant for t in ctx.txns}
    changes: list[dict] = []
    for clause in re.split(r"\band\b|,|\bthen\b", message):
        lower = clause.lower()
        merchant = find_merchant(clause, merchants)
        category = find_category(clause)
        percent = parse_percent(clause)
        money = parse_money(clause)
        if (
            re.search(r"\b(raise|earn|made|make|got|get|bonus|pay rise|side job|income)\b", lower)
            and money
        ):
            sign = -1 if re.search(r"\b(lose|lost|less|drop|cut)\b", lower) else 1
            changes.append({"type": "income_change", "monthly_cents": sign * money})
        elif re.search(r"\b(lost|lose)\b.*\b(job|income)\b", lower):
            average = tools.average_monthly(ctx.txns, ctx.today, 3)
            changes.append({"type": "income_change", "monthly_cents": -average["income_cents"]})
        elif merchant and re.search(
            r"\b(cancel\w*|stop\w*|drop\w*|quit\w*|remove\w*|get rid of)\b", lower
        ):
            changes.append({"type": "cancel_merchant", "merchant": merchant})
        elif merchant and percent:
            changes.append({"type": "cancel_merchant", "merchant": merchant, "percent": percent})
        elif category and re.search(r"\b(stop\w*|quit\w*|no more|cancel\w*|drop\w*)\b", lower):
            changes.append({"type": "cut_category", "category": category, "percent": 100.0})
        elif category and percent:
            changes.append({"type": "cut_category", "category": category, "percent": percent})
        elif money and re.search(r"\b(buy|spend|purchase|trip|new)\b", lower):
            if re.search(r"\b(month|monthly|per month)\b", lower):
                changes.append(
                    {"type": "add_recurring", "monthly_cents": money, "label": "New monthly cost"}
                )
            else:
                changes.append(
                    {"type": "one_off", "amount_cents": money, "label": "One-off purchase"}
                )
    return changes


def _afford_label(message: str) -> str:
    match = re.search(
        r"\b(?:a|an|the|for)\s+(?:\S*\d\S*\s+)?([a-z][a-z ]{2,24}?)(?:\s+(?:by|in|before|next)\b|\?|$)",
        message,
        re.I,
    )
    return match.group(1).strip() if match else "this"


def route(message: str, ctx: FinanceContext) -> ToolOutput | None:
    """Return the answer for a recognised question, or None when it needs a model."""
    period = parse_period(message, ctx.today)
    category = find_category(message)
    merchant = find_merchant(message, {t.merchant for t in ctx.txns})

    if _AFFORD.search(message) and not _WHAT_IF.search(message):
        amount = parse_money(message)
        if amount is None:
            return ToolOutput(
                "clarify",
                {},
                "Happy to check. How much will it cost, and when do you need it by?",
                suggestions=["Can I afford a $1,500 trip by March?"],
            )
        return tools.afford(
            ctx, amount, parse_future_date(message, ctx.today), _afford_label(message)
        )
    if _WHAT_IF.search(message):
        changes = _parse_changes(message, ctx)
        if changes:
            return tools.what_if(ctx, changes)
        if re.search(r"\bcancel\b.*\b(most expensive|biggest|priciest)\b", message, re.I):
            subs = [s for s in ctx.streams if s.is_subscription and s.active]
            if subs:
                top = max(subs, key=lambda s: s.monthly_cents)
                return tools.what_if(ctx, [{"type": "cancel_merchant", "merchant": top.merchant}])
        return tools.what_if(ctx, [])
    if _GOALS.search(message):
        return tools.goals(ctx)
    if _FORECAST.search(message):
        return tools.forecast(ctx)
    if _BUDGET_MAKE.search(message):
        return tools.budget_suggestions(ctx)
    if _BUDGET.search(message) and not _TIPS.search(message):
        return tools.budget_status(ctx)
    if _INSIGHTS.search(message):
        kinds = None
        if re.search(r"unusual|weird|strange|\bodd\b|suspicious|anomal|wrong", message, re.I):
            kinds = {"duplicate", "unusual", "price_increase", "low_balance"}
        elif re.search(r"\bprice|went up\b", message, re.I):
            kinds = {"price_increase"}
        elif re.search(r"\bduplicate|double", message, re.I):
            kinds = {"duplicate"}
        return tools.insights(ctx, kinds)
    if _TIPS.search(message):
        return tools.budget_tips(ctx)
    if _RECURRING.search(message) and not (period and _SPENDING.search(message)):
        return tools.recurring(ctx)
    if _INCOME.search(message):
        return tools.income(ctx, period)
    if _TOP.search(message):
        return tools.top_merchants(ctx, period)
    if _SPENDING.search(message) or ((category or merchant) and period):
        return tools.spending(ctx, period, category, merchant)
    if _OVERVIEW.search(message):
        return tools.overview(ctx)
    if merchant or category:
        return tools.spending(ctx, period, category, merchant)
    return None
