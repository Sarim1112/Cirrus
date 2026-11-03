"""Calculation tools. Each returns structured data plus a plain, fully correct written answer.

The written answer means the advisor works with no model at all, and gives a local model
something verified to rephrase instead of asking it to do arithmetic.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..categories import CATEGORIES, INCOME
from ..engine import budgets as budget_engine
from ..engine.context import FinanceContext
from ..engine.core import (
    add_months,
    average_monthly,
    by_category,
    by_merchant,
    in_range,
    income_cents,
    month_end,
    month_start,
    monthly_series,
    spending_cents,
    totals,
)
from ..engine.simulate import afford as afford_engine
from ..engine.simulate import simulate
from .parse import Period, _month_period, find_category, parse_future_date, parse_period

STALE_AFTER_DAYS = 14


@dataclass
class ToolOutput:
    name: str
    data: dict[str, Any]
    draft: str
    charts: list[dict] = field(default_factory=list)
    evidence: dict | None = None
    suggestions: list[str] = field(default_factory=list)


def _short_date(day: date | str) -> str:
    value = date.fromisoformat(day) if isinstance(day, str) else day
    return f"{value:%b} {value.day}"


def _titled(title: str) -> str:
    return title if title.endswith("?") else f"{title}."


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


def _evidence(
    ctx: FinanceContext, ids: list[str], label: str, href: str = "/transactions"
) -> dict | None:
    if not ids:
        return None
    wanted = set(ids)
    rows = sorted((t for t in ctx.txns if t.id in wanted), key=lambda t: t.date, reverse=True)
    return {
        "label": label,
        "total": len(rows),
        "href": href,
        "items": [
            {"id": t.id, "date": t.date.isoformat(), "merchant": t.merchant,
             "category": t.category, "amount_cents": t.amount_cents}
            for t in rows[:8]
        ],
    }  # fmt: skip


def _bars(title: str, rows: list[tuple[str, int]]) -> dict:
    return {
        "kind": "bars",
        "title": title,
        "rows": [{"label": label, "value_cents": value} for label, value in rows],
    }


def _no_data() -> ToolOutput:
    return ToolOutput(
        "no_data",
        {},
        "I don't have any transactions for you yet. Import a CSV or PDF statement, or load the "
        "demo data, and I can start answering from your real numbers.",
        suggestions=[],
    )


# ---------------------------------------------------------------------------------------------


def spending(
    ctx: FinanceContext,
    period: Period | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    period = period or _month_period(ctx.today, ctx.today, "this month")
    rows = in_range(ctx.txns, period.start, period.end)
    fmt = ctx.fmt
    query = f"month={period.key}&" if period.key else ""

    if category or merchant:
        scoped = [
            t
            for t in rows
            if (category is None or t.category == category)
            and (merchant is None or t.merchant == merchant)
        ]
        subject = merchant or category
        total = max(0, spending_cents(scoped))
        count = len(scoped)
        data = {
            "subject": subject,
            "period": period.name,
            "spent_cents": total,
            "purchases": count,
        }
        preposition = "at" if merchant else "on"
        draft = (
            f"You spent {fmt(total)} {preposition} {subject} {period.label}"
            f"{f' across {count} purchases' if count > 1 else ''}."
        )
        if period.key:
            before = _month_period(add_months(period.start, -1), ctx.today)
            prior_rows = [
                t
                for t in in_range(ctx.txns, before.start, before.end)
                if (category is None or t.category == category)
                and (merchant is None or t.merchant == merchant)
            ]
            if prior_rows:
                prior = max(0, spending_cents(prior_rows))
                data["previous_month_cents"] = prior
                change = total - prior
                if change:
                    data["change_cents"] = abs(change)
                    word = "more" if change > 0 else "less"
                    draft += (
                        f" That's {fmt(abs(change))} {word} than {before.label} ({fmt(prior)})."
                    )
                    if period.start == month_start(ctx.today):
                        draft += " The month isn't finished yet."
        trend = []
        for offset in range(5, -1, -1):
            start = add_months(month_start(ctx.today), -offset)
            month_rows = [
                t
                for t in in_range(ctx.txns, start, month_end(start))
                if (category is None or t.category == category)
                and (merchant is None or t.merchant == merchant)
            ]
            trend.append((f"{start:%b}", max(0, spending_cents(month_rows))))
        href = f"/transactions?{query}" + (f"q={merchant}" if merchant else f"category={category}")
        return ToolOutput(
            "spending",
            data,
            draft,
            charts=[_bars(f"{subject}, by month", trend)],
            evidence=_evidence(
                ctx,
                [t.id for t in sorted(scoped, key=lambda t: t.amount_cents)],
                f"{subject}, {period.name}",
                href,
            ),
            suggestions=[f"Give me tips to spend less on {subject}", "What if I cut this by 25%?"],
        )

    summary = totals(rows)
    categories = by_category(rows)
    top = categories[:3]
    data = {"period": period.label, **summary, "categories": categories[:8]}
    if not rows:
        return ToolOutput(
            "spending", data, f"I don't have any transactions for {period.name}.",
            suggestions=["What did I spend last month?"],
        )  # fmt: skip
    draft = f"You spent {fmt(summary['spending_cents'])} {period.label}"
    if summary["income_cents"]:
        word = "kept" if summary["net_cents"] >= 0 else "went over by"
        draft += (
            f" and brought in {fmt(summary['income_cents'])}, so you {word} "
            f"{fmt(abs(summary['net_cents']))}"
        )
    draft += "."
    if top:
        items = [f"{row['name']} ({fmt(row['amount_cents'])})" for row in top]
        draft += f" Your biggest categories were {_join(items)}."
    ranked = sorted(
        (
            t
            for t in rows
            if t.amount_cents < 0 and t.category != INCOME and t.category != "Transfers"
        ),
        key=lambda t: t.amount_cents,
    )
    return ToolOutput(
        "spending",
        data,
        draft,
        charts=[
            _bars(
                f"Spending by category, {period.name}",
                [(r["name"], r["amount_cents"]) for r in categories[:8]],
            )
        ],  # fmt: skip
        evidence=_evidence(
            ctx,
            [t.id for t in ranked[:30]],
            f"Largest purchases, {period.name}",
            f"/transactions?{query}".rstrip("?&"),
        ),  # fmt: skip
        suggestions=["Where can I cut back?", "Am I on budget?", "What's safe to spend?"],
    )


def top_merchants(ctx: FinanceContext, period: Period | None = None) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    period = period or _month_period(ctx.today, ctx.today, "this month")
    rows = in_range(ctx.txns, period.start, period.end)
    merchants = by_merchant(rows)[:8]
    fmt = ctx.fmt
    if not merchants:
        return ToolOutput("top_merchants", {"period": period.label},
                          f"I don't have any spending for {period.name}.")  # fmt: skip
    items = [f"{m['name']} ({fmt(m['amount_cents'])})" for m in merchants[:3]]
    return ToolOutput(
        "top_merchants",
        {"period": period.label, "merchants": merchants},
        f"Your top places {period.label} were {_join(items)}.",
        charts=[
            _bars(
                f"Top merchants, {period.name}",
                [(m["name"], m["amount_cents"]) for m in merchants],
            )
        ],  # fmt: skip
        suggestions=["Which of these are subscriptions?", "Where can I cut back?"],
    )


def income(ctx: FinanceContext, period: Period | None = None) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    if period:
        rows = in_range(ctx.txns, period.start, period.end)
        total = income_cents(rows)
        paid = [t for t in rows if t.category == INCOME]
        return ToolOutput(
            "income",
            {"period": period.label, "income_cents": total, "deposits": len(paid)},
            f"You brought in {fmt(total)} {period.label}.",
            evidence=_evidence(
                ctx,
                [t.id for t in paid],
                f"Income, {period.name}",
                "/transactions?category=Income",
            ),  # fmt: skip
        )
    average = average_monthly(ctx.txns, ctx.today, 3)
    streams = [s for s in ctx.streams if s.direction == "in" and s.active]
    draft = f"You bring in about {fmt(average['income_cents'])} a month on average."
    if streams:
        main = streams[0]
        draft += f" Your main income is {main.merchant}, {fmt(main.amount_cents)} {main.cadence}."
        draft += f" The next one should land around {_short_date(main.next_date)}."
    return ToolOutput(
        "income",
        {"average_income_cents": average["income_cents"],
         "streams": [{"merchant": s.merchant, "amount_cents": s.amount_cents, "cadence": s.cadence}
                     for s in streams]},
        draft,
        evidence=_evidence(ctx, streams[0].txn_ids[-6:] if streams else [], "Recent income",
                           "/transactions?category=Income"),
    )  # fmt: skip


def recurring(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    active = [s for s in ctx.streams if s.direction == "out" and s.active]
    subs = [s for s in active if s.is_subscription]
    bills = [s for s in active if not s.is_subscription]
    if not active:
        return ToolOutput("recurring", {"streams": []},
                          "I haven't found any regular bills or subscriptions yet. "
                          "I need about three months of history to spot them.")  # fmt: skip
    subs_total = sum(s.monthly_cents for s in subs)
    bills_total = sum(s.monthly_cents for s in bills)
    draft = (
        f"You have {len(subs)} subscriptions costing {fmt(subs_total)} a month "
        f"({fmt(subs_total * 12)} a year), plus {len(bills)} regular bills at about "
        f"{fmt(bills_total)} a month."
    )
    if subs:
        items = [f"{s.merchant} ({fmt(s.amount_cents)})" for s in subs[:5]]
        draft += f" Your subscriptions are {_join(items)}."
    raised = [s for s in subs if s.price_change_cents > 0]
    if raised:
        s = raised[0]
        draft += f" {s.merchant} recently went up by {fmt(s.price_change_cents)}."
    return ToolOutput(
        "recurring",
        {
            "subscriptions_monthly_cents": subs_total,
            "subscriptions_yearly_cents": subs_total * 12,
            "bills_monthly_cents": bills_total,
            "subscriptions": [
                {"merchant": s.merchant, "amount_cents": s.amount_cents, "cadence": s.cadence,
                 "monthly_cents": s.monthly_cents, "next_date": s.next_date.isoformat(),
                 "price_change_cents": s.price_change_cents}
                for s in subs
            ],
            "bills": [
                {"merchant": s.merchant, "amount_cents": s.amount_cents, "cadence": s.cadence,
                 "monthly_cents": s.monthly_cents, "next_date": s.next_date.isoformat()}
                for s in bills
            ],
        },
        draft,
        charts=[_bars("Monthly cost of subscriptions", [(s.merchant, s.monthly_cents) for s in subs])]
        if subs else [],
        evidence=_evidence(ctx, [s.txn_ids[-1] for s in active], "Latest charge for each",
                           "/transactions?category=Subscriptions"),
        suggestions=["What if I cancel the most expensive one?", "What's safe to spend?"],
    )  # fmt: skip


def budget_status(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    if not ctx.budgets:
        output = budget_suggestions(ctx)
        output.draft = "You haven't set any budgets yet. " + output.draft
        return output
    rows = budget_engine.budget_status(ctx.txns, ctx.budgets, ctx.today)
    over = [r for r in rows if r["status"] == "over"]
    watch = [r for r in rows if r["status"] == "watch"]
    ok_count = len(rows) - len(over) - len(watch)
    parts = []
    if over:
        items = [
            f"{r['category']} ({fmt(r['spent_cents'])} of {fmt(r['limit_cents'])})" for r in over
        ]
        parts.append(f"You're over budget on {_join(items)}.")
    if watch:
        items = [
            f"{r['category']} (likely {fmt(r['projected_cents'])} against {fmt(r['limit_cents'])})"
            for r in watch
        ]
        parts.append(f"Heading over: {_join(items)}.")
    if ok_count:
        word = "budget is" if ok_count == 1 else "budgets are"
        parts.append(f"{ok_count} {word} on track.")
    ids = [i for r in over + watch for i in r["txn_ids"]]
    return ToolOutput(
        "budget_status",
        {"budgets": [{k: v for k, v in r.items() if k != "txn_ids"} for r in rows]},
        " ".join(parts),
        charts=[{
            "kind": "budget",
            "title": "This month's budgets",
            "rows": [{"label": r["category"], "spent_cents": r["spent_cents"],
                      "limit_cents": r["limit_cents"], "status": r["status"]} for r in rows[:8]],
        }],
        evidence=_evidence(ctx, ids, "Spending in categories to watch"),
        suggestions=["Where can I cut back?", "What's safe to spend?"],
    )  # fmt: skip


def budget_suggestions(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    suggestions = budget_engine.suggest_budgets(ctx.txns, ctx.today, fmt)
    if not suggestions:
        return ToolOutput("budget_suggestions", {"suggestions": []},
                          "I need at least one complete month of history to suggest budgets.")  # fmt: skip
    flexible = [s for s in suggestions if s.kind == "flexible"][:4]
    saving = sum(s.saving_cents for s in suggestions)
    total = sum(s.limit_cents for s in suggestions)
    items = [f"{s.category} {fmt(s.limit_cents)}" for s in flexible]
    draft = (
        f"Based on your own history, a realistic monthly budget totals {fmt(total)}, which is "
        f"about {fmt(saving)} less than a typical month."
    )
    if items:
        draft += f" The main flexible targets are {_join(items)}."
    draft += " You can apply this on the Budgets page."
    return ToolOutput(
        "budget_suggestions",
        {"total_cents": total, "saving_cents": saving,
         "suggestions": [{"category": s.category, "limit_cents": s.limit_cents,
                          "typical_cents": s.typical_cents, "saving_cents": s.saving_cents,
                          "kind": s.kind} for s in suggestions]},
        draft,
        charts=[_bars("Suggested monthly budgets", [(s.category, s.limit_cents) for s in suggestions[:8]])],
        suggestions=["Where can I cut back?", "Am I on budget?"],
    )  # fmt: skip


def budget_tips(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    tips = budget_engine.savings_tips(ctx.txns, ctx.today, fmt)
    lines = []
    for tip in tips[:3]:
        line = (
            f"{tip['category']}: a typical month is now {fmt(tip['recent_cents'])}. Aim for "
            f"{fmt(tip['limit_cents'])} to save {fmt(tip['saving_cents'])} a month"
        )
        if tip["top_merchant"]:
            line += f". Start with {tip['top_merchant']}, your biggest spend here"
        lines.append(line + ".")
    subs = [s for s in ctx.streams if s.is_subscription and s.active]
    quiet = [i for i in ctx.insights if i["kind"] in {"forgotten", "price_increase"}]
    if quiet:
        lines.append(f"{_titled(quiet[0]['title'])} {quiet[0]['detail']}")
    elif subs:
        total = sum(s.monthly_cents for s in subs)
        lines.append(f"Subscriptions: you pay {fmt(total)} a month across {len(subs)} services.")
    if not lines:
        return ToolOutput(
            "budget_tips", {"tips": []},
            "Your flexible spending is already steady, and I don't see an obvious place to trim "
            "yet. A few more months of history will sharpen this.",
        )  # fmt: skip
    total_saving = sum(t["saving_cents"] for t in tips[:3])
    intro = (
        f"Here's where you could realistically save {fmt(total_saving)} a month "
        f"({fmt(total_saving * 12)} a year):\n\n"
        if total_saving
        else "Here's what stands out:\n\n"
    )
    draft = intro + "\n".join(f"- {line}" for line in lines)
    ids = [i for t in tips[:3] for i in t["txn_ids"][:6]]
    return ToolOutput(
        "budget_tips",
        {"total_saving_cents": total_saving, "yearly_saving_cents": total_saving * 12,
         "tips": [{k: v for k, v in t.items() if k != "txn_ids"} for t in tips[:3]],
         "extra": quiet[0] if quiet else None},
        draft,
        charts=[_bars("Possible monthly savings", [(t["category"], t["saving_cents"]) for t in tips[:3]])]
        if tips else [],
        evidence=_evidence(ctx, ids, "The purchases behind these tips"),
        suggestions=[f"What if I cut {tips[0]['category']} by 25%?" if tips else "What's safe to spend?",
                     "Show my subscriptions"],
    )  # fmt: skip


def insights(ctx: FinanceContext, kinds: set[str] | None = None) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    items = [i for i in ctx.insights if not kinds or i["kind"] in kinds]
    if not items:
        return ToolOutput("insights", {"insights": []},
                          "Nothing unusual stands out right now. Your recent spending looks normal "
                          "against your history.")  # fmt: skip
    top = items[:4]
    draft = "Here's what I'd look at:\n\n" + "\n".join(
        f"- {_titled(i['title'])} {i['detail']}" for i in top
    )
    ids = [x for i in top for x in i["txn_ids"]]
    return ToolOutput(
        "insights",
        {"insights": [{k: i[k] for k in ("kind", "severity", "title", "detail", "monthly_impact_cents")}
                      for i in top]},
        draft,
        evidence=_evidence(ctx, ids, "Transactions behind these findings"),
        suggestions=["Where can I cut back?", "Show my subscriptions"],
    )  # fmt: skip


def forecast(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    result = ctx.forecast
    if result["needs_balance"]:
        return ToolOutput(
            "forecast",
            {"needs_balance": True, "daily_variable_cents": result["daily_variable_cents"]},
            "I need your current balance to forecast this. Add it in Settings, and I'll work out "
            f"what's safe to spend. For now, your everyday spending runs about "
            f"{fmt(result['daily_variable_cents'])} a day.",
        )
    safe = result["safe_to_spend"]
    until = "payday" if safe["until_kind"] == "payday" else "the end of the month"
    if safe["shortfall_cents"]:
        draft = (
            f"Things are tight: after upcoming bills and your {fmt(ctx.buffer_cents)} buffer, you're "
            f"{fmt(safe['shortfall_cents'])} short before {until} on {_short_date(safe['until'])}."
        )
    else:
        draft = (
            f"You have {fmt(safe['amount_cents'])} safe to spend until {until} on "
            f"{_short_date(safe['until'])}, or about {fmt(safe['per_day_cents'])} a day. "
            f"You usually spend {fmt(safe['usual_per_day_cents'])} a day."
        )
    breakdown = safe["breakdown"]
    draft += (
        f" That starts from your {fmt(breakdown['balance_cents'])} balance and sets aside "
        f"{fmt(breakdown['bills_cents'])} for bills"
    )
    if breakdown["goals_cents"]:
        draft += f", {fmt(breakdown['goals_cents'])} for goals"
    if breakdown["held_back_cents"]:
        draft += f", {fmt(breakdown['held_back_cents'])} for bills due soon after"
    draft += f" and a {fmt(breakdown['buffer_cents'])} buffer."
    if result["month_end_balance_cents"] is not None:
        draft += (
            f" I expect you to finish this month at about {fmt(result['month_end_balance_cents'])}."
        )
    if result["stale_days"] > STALE_AFTER_DAYS:
        draft += (
            f" Your newest transaction is from {_short_date(result['latest_data_date'])}, so import "
            "a newer statement for a more accurate picture."
        )
    low = result["low_point"]
    if low and low["balance_cents"] < ctx.buffer_cents:
        draft += f" Watch out: your balance may dip to {fmt(low['balance_cents'])} around {_short_date(low['date'])}."
    return ToolOutput(
        "forecast",
        {"safe_to_spend": {k: v for k, v in safe.items()}, "low_point": low,
         "month_end_balance_cents": result["month_end_balance_cents"],
         "upcoming": result["upcoming"][:8]},
        draft,
        charts=[{"kind": "forecast", "title": "Projected balance",
                 "rows": result["points"][:35]}],
        suggestions=["What bills are coming up?", "Can I afford a $500 purchase next month?"],
    )  # fmt: skip


def what_if(ctx: FinanceContext, changes: list[dict]) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    if not changes:
        return ToolOutput(
            "what_if", {},
            "Tell me what to change, such as \"what if I cut dining by 30%\" or "
            "\"what if I cancel Netflix\".",
        )  # fmt: skip
    fmt = ctx.fmt
    result = simulate(ctx.txns, ctx.today, changes, ctx.balance_cents)
    delta = result["monthly_delta_cents"]
    impacts = "; ".join(
        f"{i['label']} changes your month by {fmt(i['monthly_cents'])}"
        for i in result["impacts"] if i.get("monthly_cents")
    )  # fmt: skip
    if delta > 0:
        draft = f"That would free up {fmt(delta)} a month, or {fmt(delta * 12)} a year."
    elif delta < 0:
        draft = f"That would cost you {fmt(-delta)} a month, or {fmt(-delta * 12)} a year."
    else:
        draft = "That wouldn't change your typical month."
    if impacts and len(result["impacts"]) > 1:
        draft += f" {impacts}."
    draft += (
        f" Your typical monthly surplus would go from {fmt(result['baseline']['net_cents'])} to "
        f"{fmt(result['scenario']['net_cents'])}."
    )
    for warning in result["warnings"]:
        draft += f" {warning}"
    series = result["series"]
    return ToolOutput(
        "what_if",
        {k: result[k] for k in ("baseline", "scenario", "monthly_delta_cents", "yearly_delta_cents", "impacts")},
        draft,
        charts=[{
            "kind": "scenario",
            "title": "Balance over 12 months" if result["has_balance"] else "Change in savings over 12 months",
            "rows": [{"label": r["month"], "baseline_cents": r["baseline_cents"],
                      "scenario_cents": r["scenario_cents"]} for r in series],
        }],
        suggestions=["Can I afford a $1,500 trip by March?", "Where else can I cut back?"],
    )  # fmt: skip


def afford(
    ctx: FinanceContext, amount_cents: int, by: date | None = None, label: str = "this"
) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    result = afford_engine(
        ctx.txns, ctx.today, amount_cents, by, ctx.balance_cents, ctx.buffer_cents,
        ctx.goal_plan["committed_monthly_cents"], label,
    )  # fmt: skip
    deadline = date.fromisoformat(result["by"])
    when = f"{deadline:%B %Y}"
    amount = fmt(amount_cents)
    surplus = result["monthly_surplus_cents"]
    months = result["months"]
    committed = result["committed_monthly_cents"]
    verdict = result["verdict"]
    after_goals = " after your goals" if committed else ""

    if verdict == "yes":
        draft = (
            f"Yes. You'd need to set aside {fmt(result['required_monthly_cents'])} a month to reach "
            f"{amount} by {when}, and your surplus{after_goals} is about {fmt(surplus)} a month."
        )
    elif verdict == "yes_with_savings":
        draft = (
            f"Yes, using some of your balance. Your surplus{after_goals} adds "
            f"{fmt(result['surplus_by_date_cents'])} by {when}, and the remaining "
            f"{fmt(amount_cents - result['surplus_by_date_cents'])} can come from your balance while "
            f"still keeping a {fmt(result['cushion_cents'])} cushion."
        )
    elif verdict == "with_cuts":
        cuts = [f"{c['category']} by {fmt(c['cut_cents'])}" for c in result["suggested_cuts"]]
        draft = (
            f"Yes, with some changes. You'd be {fmt(result['gap_cents'])} short by {when}, or "
            f"{fmt(result['gap_monthly_cents'])} a month. Cutting {_join(cuts)} a month closes the gap."
        )
    else:
        draft = (
            f"Not by {when}. Your surplus{after_goals} is {fmt(surplus)} a month, which leaves you "
            f"{fmt(result['gap_cents'])} short over {months} months."
        )
        if result["earliest_date"]:
            earliest = date.fromisoformat(result["earliest_date"])
            draft += f" With some trimming, {earliest:%B %Y} looks realistic."
    if not result["has_balance"]:
        draft += " I left your balance out because you haven't added it yet."
    return ToolOutput(
        "afford",
        result,
        draft,
        suggestions=["What's safe to spend?", "Where can I cut back?"],
    )


def goals(ctx: FinanceContext) -> ToolOutput:
    fmt = ctx.fmt
    plan = ctx.goal_plan
    if not plan["plans"]:
        return ToolOutput(
            "goals",
            {"monthly_surplus_cents": plan["monthly_surplus_cents"], "plans": []},
            f"You don't have any goals yet. Your typical monthly surplus is "
            f"{fmt(plan['monthly_surplus_cents'])}, so that's what you could put toward one. "
            "Add one on the Goals page.",
        )
    labels = {"done": "reached", "on_track": "on track", "tight": "a little tight",
              "behind": "behind", "open": "in progress", "paused": "paused"}  # fmt: skip
    lines = []
    for item in plan["plans"]:
        line = (
            f"{item['name']}: {fmt(item['saved_cents'])} of {fmt(item['target_cents'])}, "
            f"{labels[item['status']]}"
        )
        if item["status"] in {"on_track", "tight", "behind"}:
            line += f". It needs {fmt(item['required_monthly_cents'])} a month"
        if item["status"] in {"tight", "behind"} and item["allocated_monthly_cents"]:
            line += f", and your surplus covers {fmt(item['allocated_monthly_cents'])}"
        if item["status"] in {"tight", "behind"} and item["projected_date"]:
            line += f". At this rate you'd finish around {date.fromisoformat(item['projected_date']):%B %Y}"
        lines.append(line + ".")
    draft = (
        f"Your typical monthly surplus is {fmt(plan['monthly_surplus_cents'])}.\n\n"
        + "\n".join(f"- {line}" for line in lines)
    )
    return ToolOutput(
        "goals",
        plan,
        draft,
        charts=[{"kind": "goals", "title": "Goal progress",
                 "rows": [{"label": p["name"], "saved_cents": p["saved_cents"],
                           "target_cents": p["target_cents"], "status": p["status"]}
                          for p in plan["plans"]]}],
        suggestions=["Where can I cut back?", "What's safe to spend?"],
    )  # fmt: skip


def overview(ctx: FinanceContext) -> ToolOutput:
    if not ctx.txns:
        return _no_data()
    fmt = ctx.fmt
    period = _month_period(ctx.today, ctx.today, "this month")
    rows = in_range(ctx.txns, period.start, period.end)
    summary = totals(rows)
    series = monthly_series(ctx.txns, ctx.today, 6)
    average = average_monthly(ctx.txns, ctx.today, 3)
    draft = (
        f"So far this month you've spent {fmt(summary['spending_cents'])}. In a typical month you "
        f"spend {fmt(average['spending_cents'])} and bring in {fmt(average['income_cents'])}, "
        f"leaving {fmt(average['net_cents'])}."
    )
    safe = ctx.forecast.get("safe_to_spend")
    if safe and not safe["shortfall_cents"]:
        draft += f" You have {fmt(safe['amount_cents'])} safe to spend until {_short_date(safe['until'])}."
    top = next((i for i in ctx.insights if i["severity"] in {"alert", "watch"}), None)
    if top:
        draft += f" One thing to check: {_titled(top['title'])}"
    return ToolOutput(
        "overview",
        {"this_month": summary, "average": average, "safe_to_spend": safe, "top_insight": top},
        draft,
        charts=[{"kind": "cashflow", "title": "Income and spending",
                 "rows": [{"label": s["month"], "income_cents": s["income_cents"],
                           "spending_cents": s["spending_cents"]} for s in series]}],
        evidence=_evidence(ctx, (top or {}).get("txn_ids", []), "Behind that finding"),
        suggestions=["Where can I cut back?", "What's safe to spend?", "Anything unusual lately?"],
    )  # fmt: skip


def invest_capacity(ctx: FinanceContext) -> ToolOutput:
    """Used by the investing guardrail: state the capacity, never a pick."""
    average = average_monthly(ctx.txns, ctx.today, 3) if ctx.txns else {"net_cents": 0}
    surplus = max(0, average["net_cents"] - ctx.goal_plan["committed_monthly_cents"])
    return ToolOutput(
        "invest_capacity",
        {"surplus_cents": surplus},
        "I can't tell you what to buy or sell, as that's a job for a licensed advisor. What I can "
        f"tell you is what your budget supports: after your goals, about {ctx.fmt(surplus)} a month "
        "is free. It's worth having an emergency fund in place before putting money at risk.",
        suggestions=["What's safe to spend?", "Where can I cut back?"],
    )


def hardship(ctx: FinanceContext) -> ToolOutput:
    """Supportive and practical: state what's due, then point to free human help."""
    fmt = ctx.fmt
    lead = "That sounds really stressful, and it can be worked through one step at a time."
    if not ctx.txns:
        draft = (
            f"{lead} A non-profit credit counsellor can review your situation for free. It's also "
            "worth calling whoever you owe before a payment is missed, since many offer payment "
            "plans. If you import a statement, I'll map out what's due and where money can be freed up."
        )
        return ToolOutput("hardship", {}, draft)
    upcoming = [e for e in ctx.forecast["upcoming"] if e["amount_cents"] < 0][:4]
    items = [
        f"{e['merchant']} ({fmt(-e['amount_cents'])}, {_short_date(e['date'])})" for e in upcoming
    ]
    draft = lead
    if items:
        draft += f" Here's what's coming up next: {_join(items)}."
    cuts = budget_engine.flexible_cut_options(ctx.txns, ctx.today)[:3]
    if cuts:
        joined = _join([f"{c['category']} ({fmt(c['cut_cents'])})" for c in cuts])
        draft += f" The quickest money to free up a month is in {joined}."
    draft += (
        " Call whoever you owe before a payment is missed, since many offer payment plans. A "
        "non-profit credit counsellor can also review everything with you for free."
    )
    return ToolOutput(
        "hardship", {"upcoming": upcoming, "cuts": cuts}, draft,
        suggestions=["What bills are coming up?", "What's safe to spend?"],
    )  # fmt: skip


# ---------------------------------------------------------------------------------------------
# Tool definitions offered to a model for questions the deterministic router can't place.
# ---------------------------------------------------------------------------------------------
def _object(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


_PERIOD = {"type": "string", "description": "e.g. 'this month', 'last month', 'March 2026'"}
MODEL_TOOLS = [
    ("get_spending", "Total or filtered spending for a period.",
     _object({"period": _PERIOD, "category": {"type": "string", "enum": CATEGORIES},
              "merchant": {"type": "string"}})),
    ("get_top_merchants", "The merchants with the most spending in a period.", _object({"period": _PERIOD})),
    ("get_income", "Income for a period, or typical monthly income.", _object({"period": _PERIOD})),
    ("get_recurring", "Subscriptions and regular bills.", _object({})),
    ("get_budget_status", "How this month's budgets are going.", _object({})),
    ("get_budget_suggestions", "A personalised monthly budget.", _object({})),
    ("get_savings_tips", "The most realistic ways to spend less.", _object({})),
    ("get_insights", "Unusual charges, price rises and other findings.", _object({})),
    ("get_forecast", "Projected balance and safe-to-spend amount.", _object({})),
    ("get_goals", "Savings goals and plans.", _object({})),
    ("simulate_cut", "Effect of cutting a category by a percentage.",
     _object({"category": {"type": "string", "enum": CATEGORIES}, "percent": {"type": "number"}},
             ["category", "percent"])),
    ("simulate_cancel", "Effect of cancelling a merchant or subscription.",
     _object({"merchant": {"type": "string"}}, ["merchant"])),
    ("check_affordability", "Can the user afford an amount by a date?",
     _object({"amount": {"type": "number", "description": "Amount in dollars"},
              "by": {"type": "string", "description": "e.g. 'March', 'in 3 months'"}}, ["amount"])),
]  # fmt: skip


def model_tool_schemas() -> list[dict]:
    return [
        {"type": "function", "function": {"name": n, "description": d, "parameters": p}}
        for n, d, p in MODEL_TOOLS
    ]


def run_model_tool(ctx: FinanceContext, name: str, args: dict) -> ToolOutput | None:
    """Every tool is read-only. Arguments from a model are treated as untrusted input."""
    args = args if isinstance(args, dict) else {}
    period = parse_period(str(args.get("period", "")), ctx.today) if args.get("period") else None
    category = find_category(str(args.get("category", ""))) if args.get("category") else None
    if name == "get_spending":
        merchant = None
        if args.get("merchant"):
            wanted = str(args["merchant"]).lower()
            merchant = next((t.merchant for t in ctx.txns if t.merchant.lower() == wanted), None)
        return spending(ctx, period, category, merchant)
    if name == "get_top_merchants":
        return top_merchants(ctx, period)
    if name == "get_income":
        return income(ctx, period)
    if name == "simulate_cut" and category:
        try:
            percent = max(0.0, min(float(args.get("percent", 0)), 100.0))
        except (TypeError, ValueError):
            return None
        return what_if(ctx, [{"type": "cut_category", "category": category, "percent": percent}])
    if name == "simulate_cancel" and args.get("merchant"):
        wanted = str(args["merchant"]).lower()
        merchant = next((t.merchant for t in ctx.txns if t.merchant.lower() == wanted), None)
        if merchant is None:
            return None
        return what_if(ctx, [{"type": "cancel_merchant", "merchant": merchant}])
    if name == "check_affordability":
        try:
            amount = round(float(args.get("amount", 0)) * 100)
        except (TypeError, ValueError):
            return None
        if amount <= 0:
            return None
        return afford(ctx, amount, parse_future_date(f"by {args.get('by', '')}", ctx.today))
    simple = {
        "get_recurring": recurring,
        "get_budget_status": budget_status,
        "get_budget_suggestions": budget_suggestions,
        "get_savings_tips": budget_tips,
        "get_insights": insights,
        "get_forecast": forecast,
        "get_goals": goals,
    }
    handler = simple.get(name)
    return handler(ctx) if handler else None
