"""Read periods, amounts, dates, categories and merchants out of a question."""

import re
from dataclasses import dataclass
from datetime import date

from ..categories import CATEGORIES, TRANSFERS
from ..engine.core import add_months, month_end, month_start

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
]  # fmt: skip
_MONTH_PATTERN = "|".join(MONTH_NAMES + [m[:3] for m in MONTH_NAMES if m != "may"])

CATEGORY_ALIASES = {
    "Food Delivery": ("food delivery", "delivery", "takeout", "take-out", "take out", "uber eats",
                      "ubereats", "doordash", "skip the dishes", "skipthedishes"),
    "Dining": ("dining", "restaurant", "restaurants", "eating out", "eat out", "coffee", "cafes",
               "lunch out", "food out"),
    "Groceries": ("groceries", "grocery", "supermarket"),
    "Housing": ("housing", "rent", "mortgage"),
    "Utilities": ("utilities", "hydro", "internet", "phone bill", "electricity", "cell phone"),
    "Transport": ("transport", "transit", "gas", "fuel", "uber", "commute", "parking"),
    "Shopping": ("shopping", "clothes", "clothing", "online shopping"),
    "Subscriptions": ("subscriptions", "subscription", "streaming"),
    "Entertainment": ("entertainment", "movies", "concerts", "games", "gaming"),
    "Health": ("health", "pharmacy", "gym", "fitness", "dentist"),
    "Insurance": ("insurance",),
    "Education": ("education", "tuition", "textbooks", "courses"),
    "Travel": ("travel", "flights", "hotels", "vacation"),
    "Personal Care": ("personal care", "haircut", "salon", "beauty"),
    "Fees": ("fees", "bank fees", "overdraft"),
    "Debt Payments": ("debt", "loan", "loans", "debt payments", "student loan"),
    "Gifts & Donations": ("gifts", "gift", "donations", "charity"),
}  # fmt: skip


@dataclass
class Period:
    start: date
    end: date
    label: str
    key: str = ""

    @property
    def name(self) -> str:
        """The period as a noun, for chart titles: "May" rather than "in May"."""
        return self.label.removeprefix("in ")


def _month_period(day: date, today: date, label: str | None = None) -> Period:
    start, end = month_start(day), month_end(day)
    name = label or (f"in {start:%B}" if start.year == today.year else f"in {start:%B %Y}")
    return Period(start, end, name, f"{start.year:04d}-{start.month:02d}")


def parse_period(text: str, today: date) -> Period | None:
    lower = text.lower()
    if re.search(r"\bthis month\b|\bso far\b|\bcurrent month\b", lower):
        return _month_period(today, today, "this month")
    if re.search(r"\blast month\b|\bprevious month\b", lower):
        return _month_period(add_months(month_start(today), -1), today, "last month")
    match = re.search(
        r"\b(?:last|past|previous)\s+(\d{1,2}|two|three|four|six|twelve)\s+months?\b", lower
    )
    if match:
        word = match.group(1)
        words = {"two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}
        count = words.get(word) or int(word)
        start = add_months(month_start(today), -count)
        end = month_end(add_months(month_start(today), -1))
        return Period(start, end, f"the last {count} months")
    if re.search(r"\bthis year\b|\byear to date\b|\bytd\b", lower):
        return Period(date(today.year, 1, 1), today, "this year")
    if re.search(r"\blast year\b", lower):
        return Period(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year")
    match = re.search(
        rf"\b(?:in|for|during|of|from|on)?\s*\b({_MONTH_PATTERN})\b\.?(?:\s+(20\d{{2}}))?", lower
    )
    if match and (
        match.group(1) != "may"
        or re.search(r"\b(in|for|during|of|from) may\b|\bmay 20\d\d\b", lower)
    ):
        index = next(i for i, m in enumerate(MONTH_NAMES) if m.startswith(match.group(1)[:3])) + 1
        year = int(match.group(2)) if match.group(2) else today.year
        if not match.group(2) and date(year, index, 1) > today:
            year -= 1
        return _month_period(date(year, index, 1), today)
    return None


def parse_future_date(text: str, today: date) -> date | None:
    lower = text.lower()
    match = re.search(
        rf"\b(?:by|before|until|for|in)\s+(?:the end of\s+)?({_MONTH_PATTERN})\b\.?(?:\s+(20\d{{2}}))?",
        lower,
    )
    if match and (match.group(1) != "may" or re.search(r"\b(by|before|until|in) may\b", lower)):
        index = next(i for i, m in enumerate(MONTH_NAMES) if m.startswith(match.group(1)[:3])) + 1
        year = int(match.group(2)) if match.group(2) else today.year
        if not match.group(2) and date(year, index, 1) <= month_start(today):
            year += 1
        return month_end(date(year, index, 1))
    match = re.search(r"\b(?:in|within)\s+(\d{1,2}|a|one|two|three|six)\s+months?\b", lower)
    if match:
        words = {"a": 1, "one": 1, "two": 2, "three": 3, "six": 6}
        return add_months(today, words.get(match.group(1)) or int(match.group(1)))
    match = re.search(r"\bnext (month|year)\b", lower)
    if match:
        return add_months(today, 1 if match.group(1) == "month" else 12)
    return None


def parse_money(text: str) -> int | None:
    """First money amount in the text, in cents. Accepts $1,500, 1500 dollars and 1.5k."""
    match = re.search(
        r"(?:[$€£]|\b(?:cad|usd|eur|gbp|aed)\s?)\s?(\d[\d,]*(?:\.\d{1,2})?)\s*(k\b)?", text, re.I
    )
    if not match:
        match = re.search(r"\b(\d[\d,]*(?:\.\d{1,2})?)\s*(k\b|dollars?\b|bucks\b)", text, re.I)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    if (match.group(2) or "").lower() == "k":
        value *= 1000
    return round(value * 100)


def parse_percent(text: str) -> float | None:
    lower = text.lower()
    match = re.search(r"(\d{1,3}(?:\.\d+)?)\s?(?:%|percent)", lower)
    if match:
        return min(float(match.group(1)), 100.0)
    if re.search(r"\b(halve|half|by half|in half)\b", lower):
        return 50.0
    if re.search(r"\b(a third|one third)\b", lower):
        return 33.0
    if re.search(r"\b(a quarter|one quarter)\b", lower):
        return 25.0
    return None


def find_category(text: str) -> str | None:
    lower = text.lower()
    best, best_length = None, 0
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", lower) and len(alias) > best_length:
                best, best_length = category, len(alias)
    for category in CATEGORIES:
        if category == TRANSFERS:
            continue
        if re.search(rf"\b{re.escape(category.lower())}\b", lower) and len(category) > best_length:
            best, best_length = category, len(category)
    return best


def find_merchant(text: str, merchants: set[str]) -> str | None:
    lower = text.lower()
    matches = [
        m
        for m in merchants
        if len(m) >= 3 and re.search(rf"(?<!\w){re.escape(m.lower())}(?!\w)", lower)
    ]
    return max(matches, key=len) if matches else None
