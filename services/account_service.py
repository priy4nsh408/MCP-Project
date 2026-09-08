from decimal import Decimal

from repositories.account_repository import AccountRepository
from repositories.transaction_repository import TransactionRepository

from .dtos import AccountSummary
from .errors import AccountNotFoundError, ValidationError
from .totals import summarize_transactions, top_debit_categories


class AccountService:
    def __init__(
        self,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
    ) -> None:
        self.account_repository = account_repository
        self.transaction_repository = transaction_repository

    def get_account(self, account_id: int):
        account = self.account_repository.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(f"Account {account_id} was not found")
        return account

    def get_account_transactions(
        self, account_id: int, limit: int | None = None, offset: int = 0
    ):
        self.validate_pagination(limit, offset)
        self.get_account(account_id)
        return self.transaction_repository.get_account_transactions(
            account_id, limit=limit, offset=offset
        )

    def get_account_summary(self, account_id: int) -> AccountSummary:
        account = self.get_account(account_id)
        transactions = self.transaction_repository.get_account_transactions(account_id)
        return AccountSummary(
            account_id=account.account_id,
            customer_id=account.customer_id,
            account_type=account.account_type,
            account_balance=account.account_balance,
            transaction_summary=summarize_transactions(transactions),
            top_spending_categories=top_debit_categories(transactions, limit=5),
        )

    def calculate_spending(self, account_id: int) -> Decimal:
        transactions = self.get_account_transactions(account_id)
        return sum(
            (
                transaction.transaction_amount
                for transaction in transactions
                if transaction.transaction_type == "Debit"
            ),
            Decimal("0.00"),
        )

    def get_top_spending_categories(
        self, account_id: int, limit: int = 5
    ):
        if limit <= 0:
            raise ValidationError("limit must be greater than zero")
        transactions = self.get_account_transactions(account_id)
        return top_debit_categories(transactions, limit)

    @staticmethod
    def validate_pagination(limit: int | None, offset: int) -> None:
        if limit is not None and limit <= 0:
            raise ValidationError("limit must be greater than zero")
        if offset < 0:
            raise ValidationError("offset must not be negative")