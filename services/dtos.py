from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SpendingCategoryTotal:
    category: str
    debit_total: Decimal


@dataclass(frozen=True)
class TransactionSummary:
    transaction_count: int
    debit_count: int
    credit_count: int
    debit_total: Decimal
    credit_total: Decimal
    average_amount: Decimal


@dataclass(frozen=True)
class AccountSummary:
    account_id: int
    customer_id: int
    account_type: str
    account_balance: Decimal
    transaction_summary: TransactionSummary
    top_spending_categories: list[SpendingCategoryTotal]


@dataclass(frozen=True)
class CustomerSummary:
    customer_id: int
    customer_name: str
    branch: str
    account_count: int
    total_balance: Decimal
    transaction_summary: TransactionSummary