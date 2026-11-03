"""A fictional person's year of finances, written as raw statement rows.

The rows run through the same cleaning and categorizing pipeline as a real upload, so the demo
exercises the whole product. Dates are relative to today, so the demo never goes stale.
"""

import random
from datetime import date, timedelta

from .engine.core import add_months, month_start
from .ingest.parsers import ParsedRow


def _payday_dates(start: date, today: date) -> list[date]:
    # Biweekly Fridays, anchored so that the pattern is stable for a given date.
    anchor = date(2024, 1, 5)
    offset = (start - anchor).days % 14
    current = start + timedelta(days=(14 - offset) % 14)
    days = []
    while current <= today:
        days.append(current)
        current += timedelta(days=14)
    return days


def build_rows(today: date, months: int = 12, seed: int = 20260) -> list[ParsedRow]:
    rng = random.Random(seed)
    start = add_months(month_start(today), -months)
    rows: list[tuple[date, str, int]] = []

    def add(day: date, text: str, dollars: float) -> None:
        if start <= day <= today:
            rows.append((day, text, round(dollars * 100)))

    for payday in _payday_dates(start, today):
        add(payday, "PAYROLL DEP NORTHWIND LOGISTICS #4471", 2360.42)

    for index in range(months + 1):
        first = add_months(start, index)
        back = months - index  # months before the current one
        add(first, "PRE-AUTHORIZED RENT TRIDEL PROPERTY MGMT", -1725.00)
        add(first.replace(day=4), "ROGERS WIRELESS 8005551234 ON", -65.00)
        add(first.replace(day=6), "TEKSAVVY INTERNET PAP", -59.95)
        add(first.replace(day=12), "TORONTO HYDRO ELECTRIC SYS", -rng.uniform(58, 96))
        add(first.replace(day=15), "SONNET INSURANCE PAP 0098112", -47.50)
        add(first.replace(day=20), "NSLSC STUDENT LOAN PAYMENT", -180.00)
        # Subscriptions. Netflix's price rises three months ago.
        add(first.replace(day=3), "NETFLIX.COM 866-579-7172 ON", -(16.49 if back >= 3 else 20.99))
        add(first.replace(day=9), "SPOTIFY P2A4B19 STOCKHOLM", -11.99)
        add(first.replace(day=17), "HEADSPACE INC SUBSCRIPTION", -12.99)
        add(first.replace(day=22), "APPLE.COM/BILL ONE APPLE PARK", -3.99)
        add(first.replace(day=2), "GOODLIFE FITNESS CLUBS #182", -44.99)
        add(first.replace(day=25), "TRANSFER TO SAVINGS 90311", -300.00)
        add(first.replace(day=5), "PRESTO AUTO LOAD TTC", -128.15)

        for _ in range(rng.randint(6, 8)):
            day = first + timedelta(days=rng.randint(0, 27))
            store = rng.choice(["LOBLAWS #1032 TORONTO ON", "NO FRILLS #3321", "FOOD BASICS #662",
                                "T&T SUPERMARKET #007"])  # fmt: skip
            add(day, f"VISA DEBIT {store}", -rng.uniform(38, 118))
        for _ in range(rng.randint(5, 8)):
            day = first + timedelta(days=rng.randint(0, 27))
            place = rng.choice(["SQ *PILOT COFFEE ROASTERS", "TST* KINKA IZAKAYA", "TIM HORTONS #2244",
                                "STARBUCKS 800-782-7282", "PAI NORTHERN THAI KITCHEN",
                                "SQ *BANH MI BOYS"])  # fmt: skip
            add(day, place, -rng.uniform(5.5, 46))
        # Food delivery creeps up: this is the slow drift that the insights should catch.
        orders = 2 if back >= 6 else 4 if back >= 3 else 6
        for _ in range(orders + rng.randint(0, 1)):
            day = first + timedelta(days=rng.randint(0, 27))
            add(
                day,
                rng.choice(["UBER* EATS PENDING", "SKIPTHEDISHES 204-555"]),
                -rng.uniform(22, 44),
            )
        for _ in range(rng.randint(1, 3)):
            day = first + timedelta(days=rng.randint(0, 27))
            place = rng.choice(
                ["AMZN MKTP CA*2K4TG1", "WINNERS #0242", "DOLLARAMA #1187", "UNIQLO EATON CTR"]
            )
            add(day, place, -rng.uniform(14, 85))
        if rng.random() < 0.6:
            add(
                first + timedelta(days=rng.randint(0, 27)),
                "CINEPLEX #9321 QPS",
                -rng.uniform(16, 42),
            )
        if rng.random() < 0.5:
            add(
                first + timedelta(days=rng.randint(0, 27)),
                "SHOPPERS DRUG MART #1422",
                -rng.uniform(9, 48),
            )
        if rng.random() < 0.35:
            add(
                first + timedelta(days=rng.randint(0, 27)),
                "UBER TRIP HELP.UBER.COM",
                -rng.uniform(13, 32),
            )

    # One-offs that make the year feel lived-in, and that the insights should surface.
    add(add_months(start, 3).replace(day=14), "PORTER AIRLINES 0482231", -412.60)
    add(add_months(start, 8).replace(day=19), "AIRBNB *HM4XZ2", -388.00)
    add(add_months(start, 5).replace(day=8), "AMZN MKTP CA REFUND", 42.18)
    add(today - timedelta(days=6), "BEST BUY #0961 TORONTO ON", -489.99)
    duplicate_day = today - timedelta(days=11)
    add(duplicate_day, "ROAD RUNNER BIKE SHOP", -86.40)
    add(duplicate_day + timedelta(days=1), "ROAD RUNNER BIKE SHOP", -86.40)

    rows.sort(key=lambda r: r[0])
    return [ParsedRow(day, text, cents) for day, text, cents in rows]


DEMO_BALANCE_CENTS = 186_420
DEMO_GOALS = [
    # name, target cents, saved cents, months away
    ("Lisbon trip", 180_000, 62_000, 5),
    ("Emergency fund", 600_000, 215_000, 14),
]
