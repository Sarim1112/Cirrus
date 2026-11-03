"""SQLAlchemy models. Every row of personal data carries a user_id and cascades on delete."""

from datetime import date as DateValue
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, utcnow


def _pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def _owner() -> Mapped[str]:
    return mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _pk()
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    balance_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    balance_as_of: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    safety_buffer_cents: Mapped[int] = mapped_column(BigInteger, default=10_000)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the cookie value is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    filename: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(10))
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    """Amounts are integer cents: negative is money out, positive is money in."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_txn_user_dedupe"),
        Index("ix_txn_user_date", "user_id", "date"),
    )

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    import_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    date: Mapped[DateValue] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    raw_description: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    category_source: Mapped[str] = mapped_column(String(10), default="rule")
    dedupe_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MerchantRule(Base):
    """A category correction the user made, applied to past and future transactions."""

    __tablename__ = "merchant_rules"
    __table_args__ = (UniqueConstraint("user_id", "merchant", name="uq_rule_user_merchant"),)

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    merchant: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_budget_user_category"),)

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    category: Mapped[str] = mapped_column(String(40))
    limit_cents: Mapped[int] = mapped_column(BigInteger)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    name: Mapped[str] = mapped_column(String(80))
    target_cents: Mapped[int] = mapped_column(BigInteger)
    saved_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    target_date: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DismissedInsight(Base):
    __tablename__ = "dismissed_insights"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_dismissed_user_key"),)

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    key: Mapped[str] = mapped_column(String(160))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = _owner()
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
