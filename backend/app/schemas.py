"""Request bodies. Responses are plain dicts built by the routers."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .categories import CATEGORIES, SPENDING_CATEGORIES

Password = Annotated[str, Field(min_length=10, max_length=200)]
Cents = Annotated[int, Field(ge=-100_000_000_000, le=100_000_000_000)]
PositiveCents = Annotated[int, Field(gt=0, le=100_000_000_000)]
CURRENCIES = {"CAD", "USD", "EUR", "GBP", "AUD", "AED", "PKR", "INR", "SAR"}


class RegisterBody(BaseModel):
    email: EmailStr
    password: Password
    display_name: str = Field(default="", max_length=80)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class ForgotBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    token: str = Field(max_length=200)
    password: Password


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: Password


class SettingsBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    currency: str | None = None
    balance_cents: Cents | None = None
    clear_balance: bool = False
    safety_buffer_cents: Annotated[int, Field(ge=0, le=100_000_000)] | None = None

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str | None) -> str | None:
        if value is not None and value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class DeleteAccountBody(BaseModel):
    password: str = Field(max_length=200)


class TransactionUpdate(BaseModel):
    category: str
    apply_to_merchant: bool = True

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("Unknown category")
        return value


class TransactionCreate(BaseModel):
    date: date
    description: str = Field(min_length=1, max_length=200)
    amount_cents: Cents
    category: str | None = None

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str | None) -> str | None:
        if value is not None and value not in CATEGORIES:
            raise ValueError("Unknown category")
        return value


class BudgetItem(BaseModel):
    category: str
    limit_cents: PositiveCents

    @field_validator("category")
    @classmethod
    def _spending_category(cls, value: str) -> str:
        if value not in SPENDING_CATEGORIES:
            raise ValueError("Budgets apply to spending categories only")
        return value


class BudgetsBody(BaseModel):
    budgets: list[BudgetItem] = Field(max_length=30)


class GoalBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_cents: PositiveCents
    saved_cents: Annotated[int, Field(ge=0, le=100_000_000_000)] = 0
    target_date: date | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_cents: PositiveCents | None = None
    saved_cents: Annotated[int, Field(ge=0, le=100_000_000_000)] | None = None
    target_date: date | None = None
    clear_date: bool = False


class ScenarioChange(BaseModel):
    type: Literal["cut_category", "cancel_merchant", "income_change", "add_recurring", "one_off"]
    category: str | None = None
    merchant: str | None = Field(default=None, max_length=120)
    percent: Annotated[float, Field(ge=0, le=100)] | None = None
    monthly_cents: Cents | None = None
    amount_cents: PositiveCents | None = None
    label: str | None = Field(default=None, max_length=80)
    month_offset: Annotated[int, Field(ge=0, le=12)] | None = None


class SimulateBody(BaseModel):
    changes: list[ScenarioChange] = Field(min_length=1, max_length=10)


class AffordBody(BaseModel):
    amount_cents: PositiveCents
    by: date | None = None
    label: str = Field(default="this", max_length=60)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
