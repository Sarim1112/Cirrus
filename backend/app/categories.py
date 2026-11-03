"""The fixed category list and how each category behaves in the analytics."""

INCOME = "Income"
TRANSFERS = "Transfers"
OTHER = "Other"

CATEGORIES = [
    "Housing",
    "Utilities",
    "Groceries",
    "Dining",
    "Food Delivery",
    "Transport",
    "Shopping",
    "Subscriptions",
    "Entertainment",
    "Health",
    "Insurance",
    "Education",
    "Travel",
    "Personal Care",
    "Fees",
    "Debt Payments",
    "Gifts & Donations",
    INCOME,
    TRANSFERS,
    OTHER,
]

NON_SPENDING = {INCOME, TRANSFERS}
FIXED = {"Housing", "Utilities", "Insurance", "Debt Payments", "Education"}
ESSENTIAL = FIXED | {"Groceries", "Health", "Transport"}
SPENDING_CATEGORIES = [c for c in CATEGORIES if c not in NON_SPENDING]
