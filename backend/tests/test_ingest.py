import io
from datetime import date

import pytest
from fpdf import FPDF

from app.ingest.merchants import categorize, clean_merchant
from app.ingest.parsers import StatementError, parse_csv, parse_pdf, parse_statement
from app.ingest.pipeline import prepare_rows
from app.ingest.values import date_order_is_ambiguous, detect_date_order, parse_amount, parse_date


@pytest.mark.parametrize(
    ("raw", "cents"),
    [
        ("12.34", 1234),
        ("$1,234.56", 123456),
        ("(12.34)", -1234),
        ("-12.34", -1234),
        ("12.34-", -1234),
        ("−12.34", -1234),
        ("1.234,56", 123456),
        ("1 234,56", 123456),
        ("12,5", 1250),
        ("1,234", 123400),
        ("12.34 CR", 1234),
        ("12.34 DR", -1234),
        ("CAD 50", 5000),
        ("", None),
        ("-", None),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


def test_parse_amount_has_no_float_rounding_error():
    assert parse_amount("19.99") == 1999
    assert parse_amount("1.10") == 110
    assert parse_amount("4.35") == 435


def test_date_order_detection():
    assert detect_date_order(["13/01/2026", "02/02/2026"]) == "dmy"
    assert detect_date_order(["01/13/2026", "02/02/2026"]) == "mdy"
    assert detect_date_order(["2026-01-13"]) == "ymd"
    assert date_order_is_ambiguous(["01/02/2026", "03/04/2026"])
    assert not date_order_is_ambiguous(["13/02/2026"])


@pytest.mark.parametrize(
    ("raw", "order", "expected"),
    [
        ("2026-03-05", "mdy", date(2026, 3, 5)),
        ("2026-03-05T10:00:00", "mdy", date(2026, 3, 5)),
        ("03/05/2026", "mdy", date(2026, 3, 5)),
        ("03/05/2026", "dmy", date(2026, 5, 3)),
        ("03/05/26", "mdy", date(2026, 3, 5)),
        ("Mar 5, 2026", "mdy", date(2026, 3, 5)),
        ("5 Mar 2026", "mdy", date(2026, 3, 5)),
        ("20260305", "mdy", date(2026, 3, 5)),
        ("13/13/2026", "mdy", None),
        ("nope", "mdy", None),
    ],
)
def test_parse_date(raw, order, expected):
    assert parse_date(raw, order) == expected


@pytest.mark.parametrize(
    ("raw", "merchant", "category"),
    [
        ("NETFLIX.COM 866-579-7172 ON", "Netflix", "Subscriptions"),
        ("UBER* EATS PENDING", "Uber Eats", "Food Delivery"),
        ("UBER TRIP HELP.UBER.COM", "Uber", "Transport"),
        ("AMZN MKTP CA*2K4TG1", "Amazon", "Shopping"),
        ("VISA DEBIT LOBLAWS #1032 TORONTO ON", "Loblaws", "Groceries"),
        ("TST* KINKA IZAKAYA", "Kinka Izakaya", "Dining"),
        ("SQ *BANH MI BOYS", "Banh Mi Boys", "Dining"),
        ("PAYROLL DEP NORTHWIND LOGISTICS #4471", "Payroll", "Income"),
        ("INTERAC E-TRANSFER JOHN SMITH 4819", "Interac e-Transfer", "Transfers"),
        ("TRANSFER TO SAVINGS 90311", "Transfer", "Transfers"),
        ("PAYMENT - THANK YOU", "Credit card payment", "Transfers"),
        ("PRE-AUTHORIZED RENT TRIDEL PROPERTY MGMT", "Rent", "Housing"),
    ],
)
def test_merchant_cleaning(raw, merchant, category):
    cleaned = clean_merchant(raw)
    assert cleaned == merchant
    assert categorize(raw, cleaned, -100, {})[0] == category


def test_personal_details_dont_survive_cleaning():
    assert "SMITH" not in clean_merchant("INTERAC E-TRANSFER JOHN SMITH").upper()
    assert "4519" not in clean_merchant("ACME STORE 4519012345678901")


def test_merchant_name_cant_carry_markup():
    assert "<" not in clean_merchant("<script>alert(1)</script> SHOP")


def test_user_rule_wins_over_builtin():
    assert categorize("NETFLIX.COM", "Netflix", -100, {"Netflix": "Entertainment"}) == (
        "Entertainment",
        "user",
    )


def test_csv_standard_header():
    content = b"Date,Description,Amount,Balance\n2026-01-05,NETFLIX.COM,-16.49,1000.00\n2026-01-06,PAYROLL,2000.00,3000.00\n"
    result = parse_csv(content)
    assert [r.amount_cents for r in result.rows] == [-1649, 200000]
    assert result.rows[1].balance_cents == 300000


def test_csv_debit_and_credit_columns():
    content = b"Transaction Date,Details,Withdrawals,Deposits\n01/15/2026,LOBLAWS,52.10,\n01/16/2026,PAYROLL,,1800.00\n"
    assert [r.amount_cents for r in parse_csv(content).rows] == [-5210, 180000]


def test_csv_headerless_bank_export():
    content = b"01/15/2026,LOBLAWS #12,52.10,,947.90\n01/16/2026,PAYROLL DEP,,1800.00,2747.90\n01/17/2026,SHELL,40.00,,2707.90\n"
    result = parse_csv(content)
    assert [r.amount_cents for r in result.rows] == [-5210, 180000, -4000]
    assert result.rows[-1].balance_cents == 270790


def test_csv_preamble_semicolons_and_bom():
    content = "﻿Account;12345\n\nDate;Description;Amount\n05/01/2026;Café;-1.234,56\n13/01/2026;Shop;-10,00\n".encode()
    result = parse_csv(content)
    assert result.date_order == "dmy"
    assert result.rows[0].date == date(2026, 1, 5)
    assert result.rows[0].amount_cents == -123456


def test_csv_latin1_and_bad_rows_are_counted():
    content = "Date,Description,Amount\n2026-01-05,Caf\xe9,-5.00\nnot a date,Shop,-1.00\n".encode(
        "latin-1"
    )
    result = parse_csv(content)
    assert len(result.rows) == 1
    assert result.failed_rows == 1
    assert "Caf" in result.rows[0].description


def test_csv_flags_reversed_credit_card_exports():
    rows = "".join(f"2026-01-{d:02d},SHOP {d},{d}.50\n" for d in range(1, 11))
    assert parse_csv(f"Date,Description,Amount\n{rows}".encode()).amounts_look_reversed


def test_csv_dr_cr_type_column():
    content = b"Date,Description,Amount,Type\n2026-01-05,SHOP,10.00,debit\n2026-01-06,REFUND,4.00,credit\n"
    assert [r.amount_cents for r in parse_csv(content).rows] == [-1000, 400]


@pytest.mark.parametrize(
    "content",
    [b"", b"just,some,words\nwith,no,numbers\n", b"Date,Description,Amount\nbad,bad,bad\n"],
)
def test_csv_errors_are_helpful(content):
    with pytest.raises(StatementError):
        parse_csv(content)


def _pdf(lines: list[str]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in lines:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_pdf_with_running_balance_infers_direction():
    content = _pdf(
        [
            "Chequing statement January 2026",
            "Opening balance 1,000.00",
            "Jan 05 NETFLIX.COM 16.49 983.51",
            "Jan 06 PAYROLL DEP 2,000.00 2,983.51",
            "Jan 07 LOBLAWS 52.10 2,931.41",
            "Closing balance 2,931.41",
        ]
    )
    result = parse_pdf(content)
    assert [r.amount_cents for r in result.rows] == [-1649, 200000, -5210]
    assert result.rows[0].date == date(2026, 1, 5)


def test_pdf_credit_card_crossing_new_year():
    content = _pdf(
        [
            "Visa statement period Dec 2025 to Jan 2026",
            "Dec 30 AMAZON 20.00",
            "Jan 02 SHELL 40.00",
            "Jan 05 PAYMENT - THANK YOU 60.00",
        ]
    )
    rows = parse_pdf(content).rows
    assert rows[0].date == date(2025, 12, 30)
    assert rows[1].date == date(2026, 1, 2)
    assert [r.amount_cents for r in rows] == [-2000, -4000, 6000]


def test_pdf_sections_set_direction():
    content = _pdf(
        [
            "Statement for 2026",
            "Withdrawals",
            "01/05 COFFEE SHOP 5.00",
            "Deposits",
            "01/06 EMPLOYER INC 900.00",
        ]
    )
    assert [r.amount_cents for r in parse_pdf(content).rows] == [-500, 90000]


def test_pdf_without_text_explains_what_to_do():
    pdf = FPDF()
    pdf.add_page()
    buffer = io.BytesIO(bytes(pdf.output()))
    with pytest.raises(StatementError, match="scan"):
        parse_pdf(buffer.getvalue())


def test_damaged_pdf_is_a_clean_error():
    with pytest.raises(StatementError):
        parse_pdf(b"%PDF-1.7 this is not a real pdf")


def test_unknown_file_type_is_rejected():
    with pytest.raises(StatementError):
        parse_statement("photo.png", b"\x89PNG")


def test_same_day_duplicates_are_kept_but_reimports_are_not():
    content = b"Date,Description,Amount\n2026-01-05,COFFEE,-4.00\n2026-01-05,COFFEE,-4.00\n"
    rows = parse_csv(content).rows
    first = {p.dedupe_hash for p in prepare_rows(rows, {})}
    second = {p.dedupe_hash for p in prepare_rows(rows, {})}
    assert len(first) == 2
    assert first == second


def test_reverse_amounts():
    rows = parse_csv(b"Date,Description,Amount\n2026-01-05,COFFEE,4.00\n").rows
    assert prepare_rows(rows, {}, flip=True)[0].row.amount_cents == -400
