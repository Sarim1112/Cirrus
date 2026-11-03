"""Parse CSV and PDF statements into a common row format."""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import pdfplumber

from .values import date_order_is_ambiguous, detect_date_order, parse_amount, parse_date


class StatementError(ValueError):
    """A problem with the uploaded file, with a message the user can act on."""


@dataclass
class ParsedRow:
    date: date
    description: str
    amount_cents: int
    balance_cents: int | None = None


@dataclass
class ParseResult:
    source_type: str
    rows: list[ParsedRow] = field(default_factory=list)
    mapping: dict[str, str | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failed_rows: int = 0
    total_rows: int = 0
    date_order: str = "mdy"
    date_order_ambiguous: bool = False
    amounts_look_reversed: bool = False


_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "transaction date", "trans date", "posting date", "posted date", "post date",
             "value date", "booking date", "date posted", "completed date", "started date"),
    "description": ("description", "merchant", "payee", "name", "details", "transaction",
                    "memo", "narrative", "transaction description", "description 1", "reference",
                    "particulars"),
    "description2": ("description 2", "memo", "notes", "additional info"),
    "amount": ("amount", "transaction amount", "amt", "cad$", "cad", "usd$", "value",
               "amount (cad)", "amount (usd)"),
    "debit": ("debit", "withdrawal", "withdrawals", "money out", "paid out", "debit amount", "out",
              "withdrawn"),
    "credit": ("credit", "deposit", "deposits", "money in", "paid in", "credit amount", "in"),
    "balance": ("balance", "running balance", "available balance", "closing balance"),
    "type": ("type", "transaction type", "dr/cr", "cr/dr", "debit/credit"),
}  # fmt: skip


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            if encoding == "utf-16" and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


def _dialect_delimiter(text: str) -> str:
    """Pick the delimiter that splits the most lines into the same number of columns."""
    lines = [line for line in text.splitlines()[:40] if line.strip()]
    best, best_score = ",", (0, 0)
    for delimiter in ",;\t|":
        widths = Counter(len(row) for row in csv.reader(lines, delimiter=delimiter))
        widths.pop(1, None)
        if not widths:
            continue
        width, count = max(widths.items(), key=lambda item: (item[1], item[0]))
        if (count, width) > best_score:
            best, best_score = delimiter, (count, width)
    return best


def _match_header(cells: list[str]) -> dict[str, int] | None:
    normalised = [re.sub(r"\s+", " ", c.strip().lower()).strip(" :") for c in cells]
    mapping: dict[str, int] = {}
    for key, names in _ALIASES.items():
        for name in names:
            if name in normalised and normalised.index(name) not in mapping.values():
                mapping[key] = normalised.index(name)
                break
    has_money = "amount" in mapping or "debit" in mapping or "credit" in mapping
    return mapping if "date" in mapping and has_money else None


def _guess_headerless(rows: list[list[str]]) -> dict[str, int] | None:
    """Support banks that export date,description,debit,credit,balance with no header row."""
    sample = rows[:30]
    if not sample:
        return None
    width = max(len(r) for r in sample)

    def score(index: int, test) -> float:
        return sum(1 for r in sample if index < len(r) and test(r[index])) / len(sample)

    date_col = next((i for i in range(width) if score(i, lambda v: parse_date(v)) >= 0.8), None)
    if date_col is None:
        return None
    description_col = next(
        (
            i
            for i in range(width)
            if i != date_col and score(i, lambda v: bool(re.search("[A-Za-z]{2}", v))) >= 0.8
        ),
        None,
    )
    if description_col is None:
        return None
    money = [
        i
        for i in range(width)
        if i not in (date_col, description_col)
        and score(i, lambda v: not v.strip() or parse_amount(v) is not None) >= 0.95
        and score(i, lambda v: parse_amount(v) is not None) > 0
    ]
    if not money:
        return None
    mapping = {"date": date_col, "description": description_col}
    if len(money) == 1:
        mapping["amount"] = money[0]
    elif len(money) == 2:
        # Either amount + balance, or debit + credit. Debit/credit columns are half empty.
        if score(money[1], lambda v: bool(v.strip())) > 0.9:
            mapping["amount"], mapping["balance"] = money[0], money[1]
        else:
            mapping["debit"], mapping["credit"] = money[0], money[1]
    else:
        mapping["debit"], mapping["credit"], mapping["balance"] = money[0], money[1], money[2]
    return mapping


def _row_amount(cells: list[str], mapping: dict[str, int]) -> int | None:
    def cell(key: str) -> str | None:
        index = mapping.get(key)
        return cells[index] if index is not None and index < len(cells) else None

    if "amount" in mapping:
        amount = parse_amount(cell("amount"))
        if amount is None:
            return None
        marker = (cell("type") or "").strip().lower()
        if marker in {"debit", "dr", "d", "withdrawal", "purchase", "sale"}:
            return -abs(amount)
        if marker in {"credit", "cr", "c", "deposit"}:
            return abs(amount)
        return amount
    debit, credit = parse_amount(cell("debit")), parse_amount(cell("credit"))
    if debit:
        return -abs(debit)
    if credit:
        return abs(credit)
    if debit == 0 or credit == 0:
        return 0
    return None


def parse_csv(content: bytes, date_order: str | None = None) -> ParseResult:
    text = _decode(content)
    delimiter = _dialect_delimiter(text)
    table = [
        r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)
    ]
    if not table:
        raise StatementError("This file is empty. Export your statement again and retry.")

    # Some banks put account details above the header, so scan the first rows for it.
    header_index, mapping = None, None
    for index, row in enumerate(table[:15]):
        mapping = _match_header(row)
        if mapping:
            header_index = index
            break
    if mapping is None:
        mapping = _guess_headerless(table)
        header_index = -1
    if mapping is None:
        raise StatementError(
            "Couldn't find date and amount columns. Check the file has a date, a description "
            "and an amount or debit/credit columns."
        )

    body = table[header_index + 1 :]
    headers = table[header_index] if header_index >= 0 else None
    result = ParseResult(source_type="csv", total_rows=len(body))
    result.mapping = {
        key: (headers[index].strip() if headers else f"Column {index + 1}")
        for key, index in mapping.items()
    }
    samples = [r[mapping["date"]] for r in body[:400] if mapping["date"] < len(r)]
    result.date_order_ambiguous = date_order_is_ambiguous(samples)
    result.date_order = date_order or detect_date_order(samples)

    for cells in body:
        parsed_date = parse_date(
            cells[mapping["date"]] if mapping["date"] < len(cells) else None, result.date_order
        )
        amount = _row_amount(cells, mapping)
        parts = [
            cells[mapping[k]].strip()
            for k in ("description", "description2")
            if k in mapping and mapping[k] < len(cells)
        ]
        description = " ".join(dict.fromkeys(p for p in parts if p)) or "Unknown"
        if parsed_date is None or amount is None:
            result.failed_rows += 1
            continue
        if amount == 0:
            result.total_rows -= 1
            continue
        balance = None
        if "balance" in mapping and mapping["balance"] < len(cells):
            balance = parse_amount(cells[mapping["balance"]])
        result.rows.append(ParsedRow(parsed_date, description[:500], amount, balance))

    if not result.rows:
        raise StatementError("No transactions could be read from this file. Check its format.")
    if result.failed_rows:
        result.warnings.append(f"{result.failed_rows} rows couldn't be read and will be skipped.")
    if result.date_order_ambiguous and not date_order:
        result.warnings.append(
            "Every date fits both month/day and day/month. Check the order below is right."
        )
    if "amount" in mapping and "balance" not in mapping:
        positives = sum(1 for r in result.rows if r.amount_cents > 0)
        result.amounts_look_reversed = positives / len(result.rows) > 0.8
        if result.amounts_look_reversed:
            result.warnings.append(
                "Most amounts are positive, which is common on credit card exports. "
                "If purchases show as money in below, turn on 'Reverse amounts'."
            )
    return result


# ---------------------------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------------------------

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
)}  # fmt: skip
_MONEY = r"\(?-?[$]?\s?\d{1,3}(?:[, ]\d{3})*\.\d{2}\)?-?(?:\s?(?:CR|DR))?"
_LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?|"
    r"[A-Za-z]{3,9}\.?\s+\d{1,2}(?:,?\s+\d{4})?|\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?)\s+"
    r"(?:(?:\d{1,2}[/\-]\d{1,2}|[A-Za-z]{3}\.?\s+\d{1,2})\s+)?"
    rf"(?P<desc>.+?)\s+(?P<amounts>{_MONEY}(?:\s+{_MONEY})*)\s*$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d{2})\b")
_MONEY_FIND = re.compile(_MONEY, re.IGNORECASE)
_SKIP = re.compile(r"opening balance|closing balance|balance forward|total|subtotal", re.IGNORECASE)
_CREDIT_WORDS = re.compile(
    r"payment - thank|payment received|deposit|payroll|refund|credit\b|e-transfer from|interest paid",
    re.IGNORECASE,
)
_DEBIT_SECTION = re.compile(r"withdrawals?|purchases?|debits?|new charges", re.IGNORECASE)
_CREDIT_SECTION = re.compile(r"deposits?|credits?|payments? (and|&) credits", re.IGNORECASE)


def _pdf_date(raw: str, statement_year: int, order: str, last: date | None) -> date | None:
    raw = raw.strip().replace(".", "")
    if _YEAR.search(raw) or re.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$", raw):
        return parse_date(raw.replace(",", ""), order)
    words = raw.split()
    if len(words) == 2:
        month_word, day_word = words if words[0][:1].isalpha() else words[::-1]
        month = _MONTHS.get(month_word[:3].lower())
        if month and day_word.isdigit():
            return _with_year(statement_year, month, int(day_word), last)
    match = re.match(r"^(\d{1,2})[/\-](\d{1,2})$", raw)
    if match:
        a, b = int(match.group(1)), int(match.group(2))
        month, day = (b, a) if order == "dmy" else (a, b)
        return _with_year(statement_year, month, day, last)
    return None


def _with_year(year: int, month: int, day: int, last: date | None) -> date | None:
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    # A statement that crosses New Year: December rows use the earlier year.
    if last is not None and (last - value).days > 180:
        return _with_year(year + 1, month, day, None)
    return value


def parse_pdf(content: bytes, max_pages: int = 100, date_order: str | None = None) -> ParseResult:
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if len(pdf.pages) > max_pages:
                raise StatementError(f"This PDF has more than {max_pages} pages.")
            lines: list[str] = []
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
    except StatementError:
        raise
    except Exception as exc:  # pdfplumber raises many low-level types on damaged files
        raise StatementError("This PDF couldn't be opened. Export it again or use CSV.") from exc

    if not any(line.strip() for line in lines):
        raise StatementError(
            "This PDF has no readable text, so it's probably a scan. Download a CSV from your bank."
        )

    years = _YEAR.findall("\n".join(lines[:60]))
    year = int(years[0]) if years else date.today().year
    numeric_samples = [m.group("date") for m in (_LINE.match(line.strip()) for line in lines) if m]
    order = date_order or detect_date_order(numeric_samples)

    result = ParseResult(source_type="pdf", date_order=order)
    section_sign = 0
    last_date: date | None = None
    previous_balance: int | None = None
    pending: list[ParsedRow] = []
    needs_review = 0

    for raw_line in lines:
        line = raw_line.strip()
        if len(line) < 60 and not _MONEY_FIND.search(line):
            if _CREDIT_SECTION.search(line):
                section_sign = 1
            elif _DEBIT_SECTION.search(line):
                section_sign = -1
        if _SKIP.search(line):
            opening = _MONEY_FIND.findall(line)
            if opening and re.search("opening|forward", line, re.IGNORECASE):
                previous_balance = parse_amount(opening[-1])
            continue
        match = _LINE.match(line)
        if not match:
            continue
        parsed_date = _pdf_date(match.group("date"), year, order, last_date)
        if parsed_date is None:
            continue
        amounts = _MONEY_FIND.findall(match.group("amounts"))
        value = parse_amount(amounts[0])
        balance = parse_amount(amounts[-1]) if len(amounts) >= 2 else None
        if value is None or value == 0:
            continue
        description = match.group("desc").strip()
        last_date = parsed_date
        result.total_rows += 1

        signed = value
        explicit = value < 0 or amounts[0].upper().endswith(("CR", "DR"))
        if balance is not None and previous_balance is not None:
            # The balance change is the most reliable evidence of direction.
            delta = balance - previous_balance
            signed = abs(value) if delta > 0 else -abs(value)
        elif explicit:
            signed = abs(value) if amounts[0].upper().endswith("CR") else value
        elif section_sign:
            signed = section_sign * abs(value)
        elif _CREDIT_WORDS.search(description):
            signed = abs(value)
        else:
            signed = -abs(value)
            needs_review += 1
        previous_balance = balance if balance is not None else previous_balance
        pending.append(ParsedRow(parsed_date, description[:500], signed, balance))

    if not pending:
        raise StatementError(
            "Couldn't find transaction lines in this PDF. Download a CSV from your bank instead."
        )
    result.rows = pending
    result.mapping = {"date": "Detected", "description": "Detected", "amount": "Detected"}
    result.warnings.append("PDF layouts vary, so check the amounts below before importing.")
    if needs_review > len(pending) // 2:
        result.warnings.append(
            "This PDF doesn't show money direction clearly. Rows default to money out unless "
            "they look like deposits."
        )
    return result


def parse_statement(
    filename: str, content: bytes, date_order: str | None = None, max_pages: int = 100
) -> ParseResult:
    name = filename.lower()
    if name.endswith(".pdf") or content[:5] == b"%PDF-":
        return parse_pdf(content, max_pages=max_pages, date_order=date_order)
    if name.endswith((".csv", ".txt", ".tsv")):
        return parse_csv(content, date_order=date_order)
    raise StatementError("Upload a CSV or PDF statement.")
