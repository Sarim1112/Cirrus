"""Parsing the messy amounts and dates that bank exports contain."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_CURRENCY = re.compile(r"[$€£¥]|\b(CAD|USD|EUR|GBP|AED|PKR|INR)\b", re.IGNORECASE)
_DATE_NUMERIC = re.compile(r"^\s*(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})\s*$")

TEXT_DATE_FORMATS = (
    "%b %d %Y", "%b %d, %Y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%B %d %Y", "%B %d, %Y",
    "%d %B %Y", "%Y%m%d",
)  # fmt: skip


def parse_amount(value: str | None) -> int | None:
    """Return integer cents. Handles $1,234.56, (12.34), 12.34-, 1.234,56, 12.34 CR and DR."""
    if value is None:
        return None
    text = _CURRENCY.sub("", str(value)).strip()
    if not text or text in {"-", "--", "n/a", "N/A"}:
        return None

    negative = False
    upper = text.upper()
    if upper.endswith("CR"):
        text = text[:-2].strip()
    elif upper.endswith("DR"):
        negative = True
        text = text[:-2].strip()
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    if text.endswith("-"):
        negative, text = True, text[:-1].strip()
    if text.startswith("-") or text.startswith("−"):
        negative, text = True, text[1:].strip()
    if text.startswith("+"):
        text = text[1:].strip()

    text = text.replace(" ", "").replace(" ", "")
    if not re.fullmatch(r"[\d.,']+", text) or not re.search(r"\d", text):
        return None
    text = text.replace("'", "")

    last_comma, last_dot = text.rfind(","), text.rfind(".")
    if last_comma > last_dot:
        # A comma is the decimal mark only when followed by one or two digits: 1.234,56 or 12,5
        if len(text) - last_comma - 1 in (1, 2):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", "")
    try:
        cents = int((Decimal(text) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None
    return -cents if negative else cents


def detect_date_order(samples: list[str]) -> str:
    """Return 'ymd', 'mdy' or 'dmy' by looking for values that only fit one reading."""
    day_first, month_first = 0, 0
    for raw in samples:
        match = _DATE_NUMERIC.match(raw or "")
        if not match:
            continue
        first, second, _ = match.groups()
        if len(first) == 4:
            return "ymd"
        if int(first) > 12:
            day_first += 1
        elif int(second) > 12:
            month_first += 1
    if day_first and not month_first:
        return "dmy"
    return "mdy"


def date_order_is_ambiguous(samples: list[str]) -> bool:
    numeric = [m for m in (_DATE_NUMERIC.match(s or "") for s in samples) if m]
    if not numeric or any(len(m.group(1)) == 4 for m in numeric):
        return False
    return not any(int(m.group(1)) > 12 or int(m.group(2)) > 12 for m in numeric)


def parse_date(value: str | None, order: str = "mdy") -> date | None:
    if not value:
        return None
    text = str(value).strip()
    # Tolerate timestamps such as 2026-01-05T10:00:00 or 2026-01-05 10:00
    text = re.split(r"[T ](?=\d{1,2}:\d{2})", text)[0]
    match = _DATE_NUMERIC.match(text)
    if match:
        a, b, c = match.groups()
        try:
            if len(a) == 4:
                return date(int(a), int(b), int(c))
            year = int(c) if len(c) == 4 else 2000 + int(c)
            month, day = (int(b), int(a)) if order == "dmy" else (int(a), int(b))
            return date(year, month, day)
        except ValueError:
            return None
    cleaned = text.replace(".", "")
    for fmt in TEXT_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None
