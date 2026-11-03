"""Clean, categorize, de-duplicate and store parsed rows."""

import hashlib
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ImportBatch, MerchantRule, Transaction, User
from .merchants import categorize, clean_merchant
from .parsers import ParsedRow, ParseResult


@dataclass
class PreparedRow:
    row: ParsedRow
    merchant: str
    category: str
    source: str
    dedupe_hash: str


def user_rules(db: Session, user_id: str) -> dict[str, str]:
    rows = db.execute(select(MerchantRule).where(MerchantRule.user_id == user_id)).scalars()
    return {r.merchant: r.category for r in rows}


def prepare_rows(
    rows: list[ParsedRow], rules: dict[str, str], flip: bool = False
) -> list[PreparedRow]:
    """The occurrence counter keeps two genuine same-day coffees while still de-duplicating a
    statement that gets uploaded twice."""
    seen: Counter[tuple] = Counter()
    prepared = []
    for row in rows:
        amount = -row.amount_cents if flip else row.amount_cents
        row = ParsedRow(row.date, row.description, amount, row.balance_cents)
        merchant = clean_merchant(row.description)
        category, source = categorize(row.description, merchant, amount, rules)
        signature = (row.date.isoformat(), amount, " ".join(row.description.lower().split()))
        seen[signature] += 1
        digest = hashlib.sha256("|".join([*map(str, signature), str(seen[signature])]).encode())
        prepared.append(PreparedRow(row, merchant, category, source, digest.hexdigest()))
    return prepared


def commit_import(
    db: Session,
    user: User,
    filename: str,
    result: ParseResult,
    flip: bool = False,
) -> ImportBatch:
    prepared = prepare_rows(result.rows, user_rules(db, user.id), flip)
    existing = set(
        db.execute(select(Transaction.dedupe_hash).where(Transaction.user_id == user.id)).scalars()
    )
    batch = ImportBatch(
        user_id=user.id,
        filename=filename[:255],
        source_type=result.source_type,
        rows_total=result.total_rows,
        rows_failed=result.failed_rows,
    )
    db.add(batch)
    db.flush()
    imported = duplicates = 0
    for item in prepared:
        if item.dedupe_hash in existing:
            duplicates += 1
            continue
        existing.add(item.dedupe_hash)
        db.add(
            Transaction(
                user_id=user.id,
                import_id=batch.id,
                date=item.row.date,
                amount_cents=item.row.amount_cents,
                raw_description=item.row.description,
                merchant=item.merchant,
                category=item.category,
                category_source=item.source,
                dedupe_hash=item.dedupe_hash,
            )
        )
        imported += 1
    batch.rows_imported, batch.rows_duplicate = imported, duplicates

    # Adopt the most recent running balance, if the statement has one and it's newer.
    dated = [p.row for p in prepared if p.row.balance_cents is not None]
    if dated:
        newest = max(r.date for r in dated)
        same_day = [r for r in dated if r.date == newest]
        ascending = dated[0].date <= dated[-1].date
        latest = same_day[-1] if ascending else same_day[0]
        if user.balance_as_of is None or latest.date >= user.balance_as_of:
            user.balance_cents, user.balance_as_of = latest.balance_cents, latest.date
    db.commit()
    return batch
