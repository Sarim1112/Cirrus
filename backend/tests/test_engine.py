from datetime import date

import pytest

from app.config import Settings
from app.engine import budgets as budget_engine
from app.engine.context import make_formatter
from app.engine.core import (
    add_months,
    average_monthly,
    by_category,
    complete_months_with_data,
    spending_cents,
    totals,
)
from app.engine.forecast import build_forecast
from app.engine.goals import GoalInput, plan_goals
from app.engine.insights import (
    category_shifts,
    duplicate_charges,
    price_increases,
    subscription_review,
    unusual_transactions,
)
from app.engine.recurring import detect_recurring
from app.engine.simulate import afford, simulate

from .conftest import TODAY, fmt, txn


def monthly(amount, merchant, category, months=6, day=3, end="2026-06"):
    year, month = map(int, end.split("-"))
    start = add_months(date(year, month, 1), -(months - 1))
    return [
        txn(add_months(start, i).replace(day=day).isoformat(), amount, merchant, category)
        for i in range(months)
    ]


def salary(months=8):
    start = date(2025, 11, 1)
    return [
        txn(add_months(start, i).replace(day=1).isoformat(), 4000, "Payroll", "Income")
        for i in range(months)
    ]


# --- totals --------------------------------------------------------------------------------


def test_transfers_are_neither_income_nor_spending():
    rows = [
        txn("2026-05-01", 4000, "Payroll", "Income"),
        txn("2026-05-02", -1000, "Rent", "Housing"),
        txn("2026-05-03", -500, "Transfer", "Transfers"),
        txn("2026-05-04", 500, "Transfer", "Transfers"),
    ]
    assert totals(rows) == {"income_cents": 400000, "spending_cents": 100000, "net_cents": 300000}


def test_refunds_reduce_spending():
    rows = [txn("2026-05-01", -100), txn("2026-05-02", 40)]
    assert spending_cents(rows) == 6000
    assert by_category(rows)[0]["amount_cents"] == 6000


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


def test_only_complete_months_count_toward_averages():
    rows = [
        txn("2026-03-01", -300),
        txn("2026-04-01", -300),
        txn("2026-05-01", -300),
        txn("2026-06-14", -9000),
    ]
    assert average_monthly(rows, TODAY, 3)["spending_cents"] == 30000


def test_average_uses_only_months_with_history():
    rows = [txn("2026-05-30", -300)]
    assert complete_months_with_data(rows, TODAY, 3) == ["2026-05"]
    assert average_monthly(rows, TODAY, 3)["spending_cents"] == 30000


# --- recurring -----------------------------------------------------------------------------


def test_detects_monthly_subscription_and_next_date():
    stream = detect_recurring(monthly(-16.49, "Netflix", "Subscriptions"), TODAY)[0]
    assert stream.cadence == "monthly"
    assert stream.amount_cents == 1649
    assert stream.is_subscription and stream.active
    assert stream.next_date == date(2026, 7, 3)


def test_detects_biweekly_income():
    rows = [txn(f"2026-{m}", 2000, "Payroll", "Income") for m in
            ("03-06", "03-20", "04-03", "04-17", "05-01", "05-15", "05-29", "06-12")]  # fmt: skip
    stream = detect_recurring(rows, TODAY)[0]
    assert stream.cadence == "biweekly"
    assert stream.direction == "in"
    assert stream.monthly_cents == round(200000 * 30.44 / 14)
    assert stream.next_date == date(2026, 6, 26)


def test_weekly_grocery_habit_is_not_a_bill():
    rows = [
        txn(f"2026-05-{d:02d}", -(60 + d * 3), "Loblaws", "Groceries") for d in (1, 8, 15, 22, 29)
    ]
    assert detect_recurring(rows, TODAY) == []


def test_varying_utility_bill_still_counts_as_recurring():
    amounts = [60, 82, 74, 91, 66, 78]
    rows = [
        txn(add_months(date(2026, 1, 12), i).isoformat(), -a, "Toronto Hydro", "Utilities")
        for i, a in enumerate(amounts)
    ]
    assert detect_recurring(rows, TODAY)[0].cadence == "monthly"


def test_cancelled_subscription_becomes_inactive():
    rows = monthly(-9.99, "Old App", "Subscriptions", months=5, end="2026-02")
    rows.append(txn("2026-06-10", -5, "Other Shop", "Shopping"))
    assert not detect_recurring(rows, TODAY)[0].active


def test_old_statement_doesnt_make_bills_look_cancelled():
    rows = monthly(-9.99, "Still Paying", "Subscriptions", months=5, end="2026-02")
    assert detect_recurring(rows, TODAY)[0].active


def test_averages_stop_where_the_data_stops():
    rows = [txn(f"2026-0{m}-15", -300) for m in (1, 2, 3)] + [txn("2026-03-30", -10)]
    # Today is June, but the statement ended at March's close, so March counts in full.
    assert complete_months_with_data(rows, TODAY, 3) == ["2026-01", "2026-02", "2026-03"]
    assert average_monthly(rows, TODAY, 3)["spending_cents"] == round(91000 / 3)


def test_a_statement_ending_mid_month_leaves_that_month_out():
    rows = [txn("2026-01-15", -300), txn("2026-02-15", -300), txn("2026-03-10", -999)]
    assert complete_months_with_data(rows, TODAY, 3) == ["2026-01", "2026-02"]


def test_forecast_flags_old_data():
    rows = _forecast_rows()
    assert build_forecast(rows, date(2026, 8, 1), 100_000)["stale_days"] == 61


def test_no_budget_suggestion_is_ever_zero():
    rows = _history("Fees", [1, 2, 1, 2, 1, 2])
    assert budget_engine.suggest_budgets(rows, TODAY, fmt)[0].limit_cents >= 500


def test_two_charges_are_not_enough_for_monthly():
    assert detect_recurring(monthly(-9.99, "New App", "Subscriptions", months=2), TODAY) == []


def test_price_increase_is_found():
    rows = monthly(-16.49, "Netflix", "Subscriptions", months=4, end="2026-03")
    rows += monthly(-20.99, "Netflix", "Subscriptions", months=3, end="2026-06")
    streams = detect_recurring(rows, TODAY)
    assert streams[0].price_change_cents == 450
    insight = price_increases(streams, TODAY, fmt)[0]
    assert insight["monthly_impact_cents"] == 450
    assert "$54.00" in insight["detail"]


def test_year_end_date_handling_for_expected_dates():
    rows = [
        txn(add_months(date(2025, 12, 31), i).isoformat(), -5, "Thing", "Subscriptions")
        for i in range(6)
    ]
    stream = detect_recurring(rows, date(2026, 6, 1))[0]
    assert stream.last_date == date(2026, 5, 31)
    assert stream.dates_between(date(2026, 6, 1), date(2026, 8, 31)) == [
        date(2026, 6, 30),
        date(2026, 7, 31),
        date(2026, 8, 31),
    ]


# --- budgets -------------------------------------------------------------------------------


def _history(category, values, end_month="2026-05"):
    year, month = map(int, end_month.split("-"))
    rows = []
    for index, value in enumerate(reversed(values)):
        day = add_months(date(year, month, 28), -index)
        if value:
            rows.append(txn(day.isoformat(), -value, "Shop", category))
    return rows


def test_fixed_costs_are_covered_not_cut():
    suggestion = budget_engine.suggest_budgets(_history("Housing", [1700] * 6), TODAY, fmt)[0]
    assert suggestion.kind == "fixed"
    assert suggestion.limit_cents == 170000
    assert suggestion.saving_cents == 0


def test_flexible_budget_targets_better_months_without_extreme_cuts():
    suggestion = budget_engine.suggest_budgets(
        _history("Dining", [300, 400, 350, 500, 380, 420]), TODAY, fmt
    )[0]
    assert suggestion.kind == "flexible"
    assert suggestion.typical_cents == 39000
    assert 39000 * 0.85 <= suggestion.limit_cents <= 39000


def test_occasional_spending_becomes_a_set_aside():
    rows = _history("Travel", [0, 0, 600, 0, 0, 0]) + _history("Groceries", [100] * 6)
    suggestion = next(
        s for s in budget_engine.suggest_budgets(rows, TODAY, fmt) if s.category == "Travel"
    )
    assert suggestion.kind == "occasional"
    assert suggestion.limit_cents == 10000


def test_budget_status_over_watch_and_ok():
    history = _history("Dining", [400] * 6) + _history("Shopping", [100] * 6)
    current = [
        txn("2026-06-05", -500, "Shop", "Dining"),
        txn("2026-06-05", -20, "Shop", "Shopping"),
    ]
    rows = budget_engine.budget_status(
        history + current, {"Dining": 40000, "Shopping": 20000}, TODAY
    )
    by_name = {r["category"]: r for r in rows}
    assert by_name["Dining"]["status"] == "over"
    assert by_name["Shopping"]["status"] == "ok"
    assert by_name["Dining"]["remaining_cents"] == -10000


def test_budget_projection_uses_history_for_pace():
    history = _history("Dining", [600] * 6)
    current = [txn("2026-06-10", -300, "Shop", "Dining")]
    row = budget_engine.budget_status(history + current, {"Dining": 50000}, TODAY)[0]
    assert row["status"] == "watch"
    assert row["projected_cents"] == 30000 + round(60000 * 0.5)


# --- forecast ------------------------------------------------------------------------------


def _forecast_rows():
    rows = []
    for i in range(6):
        month = add_months(date(2026, 1, 1), i)
        rows.append(txn(month.replace(day=1).isoformat(), -1000, "Landlord", "Housing"))
        if month.month < 6:
            rows.append(txn(month.replace(day=20).isoformat(), 3000, "Payroll", "Income"))
    return rows


def test_forecast_needs_a_balance():
    result = build_forecast(_forecast_rows(), TODAY, None)
    assert result["needs_balance"]
    assert result["safe_to_spend"] is None
    assert result["points"] == []


def test_safe_to_spend_arithmetic():
    rows = _forecast_rows() + [txn("2026-06-10", -50, "Bills Ltd", "Utilities")]
    result = build_forecast(rows, TODAY, 200_000, buffer_cents=10_000)
    safe = result["safe_to_spend"]
    # Payday is June 20, and no bills fall before then.
    assert safe["until"] == "2026-06-20"
    assert safe["until_kind"] == "payday"
    assert safe["days"] == 5
    assert safe["amount_cents"] == 200_000 - 10_000
    assert safe["per_day_cents"] == 190_000 // 5


def test_balance_projection_applies_bills_and_income_on_their_dates():
    result = build_forecast(_forecast_rows(), TODAY, 200_000)
    points = {p["date"]: p["balance_cents"] for p in result["points"]}
    daily = result["daily_variable_cents"]
    assert daily == 0
    assert points["2026-06-20"] == 200_000 + 300_000
    assert points["2026-07-01"] == 200_000 + 300_000 - 100_000


def test_shortfall_is_reported_and_never_negative():
    rows = _forecast_rows()
    today = date(2026, 6, 28)
    safe = build_forecast(rows, today, 20_000, buffer_cents=10_000)["safe_to_spend"]
    assert safe["amount_cents"] == 0
    assert safe["shortfall_cents"] > 0


def test_goal_money_is_reserved_pro_rata():
    safe = build_forecast(_forecast_rows(), TODAY, 200_000, goal_monthly_cents=30_440)[
        "safe_to_spend"
    ]
    assert safe["breakdown"]["goals_cents"] == round(30_440 * 5 / 30.44)


def test_forecast_band_widens_over_time():
    rows = _forecast_rows() + [
        txn(f"2026-06-{d:02d}", -d * 7, "Random", "Shopping") for d in range(1, 15)
    ]
    points = build_forecast(rows, TODAY, 200_000)["points"]
    assert points[0]["high_cents"] == points[0]["low_cents"]
    assert (
        points[30]["high_cents"] - points[30]["low_cents"]
        > points[5]["high_cents"] - points[5]["low_cents"]
    )


# --- simulator and affordability -----------------------------------------------------------


def _budget_rows():
    rows = []
    for i in range(6):
        month = add_months(date(2025, 12, 1), i)
        rows += [
            txn(month.replace(day=1).isoformat(), 3000, "Payroll", "Income"),
            txn(month.replace(day=2).isoformat(), -1500, "Landlord", "Housing"),
            txn(month.replace(day=3).isoformat(), -400, "Pizza", "Dining"),
            txn(month.replace(day=4).isoformat(), -200, "Uber Eats", "Food Delivery"),
            txn(month.replace(day=5).isoformat(), -20, "Netflix", "Subscriptions"),
        ]
    return rows


def test_cut_category_arithmetic():
    result = simulate(
        _budget_rows(),
        TODAY,
        [{"type": "cut_category", "category": "Food Delivery", "percent": 50}],
    )
    assert result["monthly_delta_cents"] == 10000
    assert result["yearly_delta_cents"] == 120000
    assert result["baseline"]["net_cents"] == 88000
    assert result["scenario"]["net_cents"] == 98000


def test_cancel_recurring_uses_monthly_cost():
    result = simulate(_budget_rows(), TODAY, [{"type": "cancel_merchant", "merchant": "Netflix"}])
    assert result["monthly_delta_cents"] == 2000


def test_scenario_series_includes_one_off():
    result = simulate(
        _budget_rows(), TODAY,
        [{"type": "one_off", "amount_cents": 50000, "month_offset": 1}],
        balance_cents=100000,
    )  # fmt: skip
    assert result["series"][0]["scenario_cents"] == 100000
    assert result["series"][1]["baseline_cents"] == 188000
    assert result["series"][1]["scenario_cents"] == 138000


def test_afford_yes_from_surplus():
    result = afford(_budget_rows(), TODAY, 150000, date(2026, 9, 30), 0)
    assert result["verdict"] == "yes"
    assert result["months"] == 3
    assert result["required_monthly_cents"] == 50000


def test_afford_keeps_a_cushion_when_using_savings():
    result = afford(_budget_rows(), TODAY, 400000, date(2026, 8, 31), balance_cents=500000)
    assert result["cushion_cents"] == 212000 + 10000
    assert result["spare_balance_cents"] == 500000 - 222000
    assert result["verdict"] == "yes_with_savings"


def test_afford_suggests_cuts_for_a_small_gap():
    result = afford(_budget_rows(), TODAY, 200000, date(2026, 8, 31), balance_cents=0)
    assert result["verdict"] == "with_cuts"
    assert sum(c["cut_cents"] for c in result["suggested_cuts"]) >= result["gap_monthly_cents"]


def test_afford_says_not_yet_and_gives_a_date():
    result = afford(_budget_rows(), TODAY, 2_000_000, date(2026, 8, 31), balance_cents=0)
    assert result["verdict"] == "not_yet"
    assert result["earliest_date"] > "2026-08-31"


def test_goals_commitments_reduce_affordability():
    free = afford(_budget_rows(), TODAY, 150000, date(2026, 9, 30), 0)
    committed = afford(
        _budget_rows(), TODAY, 150000, date(2026, 9, 30), 0, committed_monthly_cents=88000
    )
    assert free["verdict"] == "yes"
    assert committed["verdict"] != "yes"


# --- goals ---------------------------------------------------------------------------------


def test_goal_on_track_and_behind():
    goals = [
        GoalInput("a", "Trip", 100000, 40000, date(2026, 9, 30)),
        GoalInput("b", "Car", 2000000, 0, date(2026, 12, 31)),
    ]
    plan = plan_goals(goals, _budget_rows(), TODAY)
    trip, car = plan["plans"]
    assert trip["required_monthly_cents"] == 20000
    assert trip["status"] == "on_track"
    assert car["status"] == "behind"
    assert car["allocated_monthly_cents"] == plan["monthly_surplus_cents"] - 20000
    assert car["cuts"]


def test_goal_plan_reacts_when_spending_rises():
    goal = [GoalInput("a", "Trip", 300000, 0, date(2026, 9, 30))]
    before = plan_goals(goal, _budget_rows(), TODAY)["plans"][0]
    extra = [
        txn(add_months(date(2026, 3, 8), i).isoformat(), -700, "Shop", "Shopping") for i in range(3)
    ]
    after = plan_goals(goal, _budget_rows() + extra, TODAY)["plans"][0]
    assert (
        before["status"] == "tight"
        or before["status"] == "on_track"
        or before["status"] == "behind"
    )
    assert after["allocated_monthly_cents"] < before["allocated_monthly_cents"]


def test_open_ended_goals_dont_lock_up_the_surplus():
    goals = [
        GoalInput("a", "Trip", 100000, 40000, date(2026, 9, 30)),
        GoalInput("b", "Someday", 5000000, 0, None),
    ]
    plan = plan_goals(goals, _budget_rows(), TODAY)
    assert plan["committed_monthly_cents"] == 20000
    assert plan["unallocated_monthly_cents"] == plan["monthly_surplus_cents"] - 20000


def test_finished_and_open_goals():
    goals = [
        GoalInput("a", "Done", 1000, 1000, None),
        GoalInput("b", "Someday", 88000, 0, None),
    ]
    done, someday = plan_goals(goals, _budget_rows(), TODAY)["plans"]
    assert done["status"] == "done"
    assert someday["status"] == "open"
    assert someday["projected_date"] == add_months(TODAY, 1).isoformat()


# --- insights ------------------------------------------------------------------------------


def test_outlier_is_flagged_and_normal_purchases_are_not():
    usual = [
        txn(f"2026-0{m}-{d:02d}", -(30 + d), "Shop", "Shopping")
        for m in (3, 4, 5)
        for d in (2, 12, 22)
    ]
    outlier = txn("2026-06-10", -489.99, "Best Buy", "Shopping")
    found = unusual_transactions([*usual, outlier], TODAY, fmt)
    assert [i["txn_ids"] for i in found] == [[outlier.id]]


def test_fixed_bills_are_never_called_unusual():
    usual = [
        txn(f"2026-0{m}-{d:02d}", -30, "Shop", "Housing") for m in (3, 4, 5) for d in (2, 12, 22)
    ]
    assert (
        unusual_transactions([*usual, txn("2026-06-10", -1700, "Rent", "Housing")], TODAY, fmt)
        == []
    )


def test_duplicate_charge_found_but_coffee_habit_ignored():
    rows = [
        txn("2026-06-01", -86.40, "Bike Shop", "Shopping"),
        txn("2026-06-02", -86.40, "Bike Shop", "Shopping"),
        txn("2026-06-03", -15.00, "Cafe", "Dining"),
        txn("2026-06-03", -15.00, "Cafe", "Dining"),
    ]
    found = duplicate_charges(rows, TODAY, fmt)
    assert len(found) == 1
    assert found[0]["severity"] == "alert"


def test_category_creep_and_wins():
    rows = []
    for offset, delivery, dining in zip(
        range(6), [100, 100, 100, 200, 200, 200], [400, 400, 400, 300, 300, 300], strict=True
    ):
        month = add_months(date(2025, 12, 28), offset).isoformat()
        rows += [
            txn(month, -delivery, "Uber Eats", "Food Delivery"),
            txn(month, -dining, "Pizza", "Dining"),
        ]
    found = {i["kind"]: i for i in category_shifts(rows, TODAY, fmt)}
    assert "up 100%" in found["creep"]["title"]
    assert found["creep"]["monthly_impact_cents"] == 10000
    assert found["win"]["severity"] == "good"


def test_subscription_review_totals_and_forgotten_flag():
    streams = detect_recurring(
        monthly(-12.99, "Headspace", "Subscriptions", months=8)
        + monthly(-20, "Netflix", "Subscriptions"),
        TODAY,
    )
    found = {i["kind"]: i for i in subscription_review(streams, TODAY, fmt)}
    assert found["subscriptions"]["monthly_impact_cents"] == sum(s.monthly_cents for s in streams)
    assert "Headspace" in found["forgotten"]["title"]


def test_formatter():
    fmt_cad = make_formatter("CAD")
    assert fmt_cad(123456) == "$1,234.56"
    assert fmt_cad(120000) == "$1,200"
    assert fmt_cad(-500) == "-$5"
    assert make_formatter("AED")(5000) == "AED 50"


def test_safe_to_spend_holds_back_for_bills_right_after_payday():
    """Rent lands soon after payday and the pay doesn't cover it, so the money must be kept."""
    rows = []
    for i in range(5):
        month = add_months(date(2026, 1, 1), i)
        rows.append(txn(month.replace(day=18).isoformat(), 500, "Payroll", "Income"))
        rows.append(txn(month.replace(day=20).isoformat(), -2000, "Landlord", "Housing"))
    safe = build_forecast(rows, TODAY, 300_000, buffer_cents=10_000)["safe_to_spend"]
    # Payday June 18, then rent June 20: 3000 + 500 - 2000 - 100 buffer = 1400.
    assert safe["until"] == "2026-06-18"
    assert safe["amount_cents"] == 140_000
    assert safe["breakdown"]["held_back_cents"] == 150_000
    breakdown = safe["breakdown"]
    assert safe["amount_cents"] == (
        breakdown["balance_cents"]
        - breakdown["bills_cents"]
        - breakdown["buffer_cents"]
        - breakdown["goals_cents"]
        - breakdown["held_back_cents"]
    )


def test_production_refuses_unsafe_settings():
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        Settings(env="production", cookie_secure=False).validate_for_runtime()
    with pytest.raises(RuntimeError, match="database password"):
        Settings(
            env="production",
            cookie_secure=True,
            database_url="postgresql+psycopg://cirrus:cirrus@db/cirrus",
        ).validate_for_runtime()
    Settings(
        env="production",
        cookie_secure=True,
        database_url="postgresql+psycopg://cirrus:long@db/cirrus",
    ).validate_for_runtime()
