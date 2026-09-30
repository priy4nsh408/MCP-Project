from datetime import date
from decimal import Decimal

from repositories.account_repository import AccountRepository
from repositories.customer_repository import CustomerRepository
from repositories.transaction_repository import TransactionRepository

from .errors import (
    AccountNotFoundError,
    CustomerNotFoundError,
    TransactionNotFoundError,
    ValidationError,
)


class TransactionService:
    def __init__(
        self,
        transaction_repository: TransactionRepository,
        account_repository: AccountRepository,
        customer_repository: CustomerRepository,
    ) -> None:
        self.transaction_repository = transaction_repository
        self.account_repository = account_repository
        self.customer_repository = customer_repository

    def get_transaction(self, transaction_id: int):
        transaction = self.transaction_repository.get_transaction(transaction_id)
        if transaction is None:
            raise TransactionNotFoundError(
                f"Transaction {transaction_id} was not found"
            )
        return transaction

    def get_account_transactions(
        self,
        account_id: int,
        limit: int | None = None,
        offset: int = 0,
        transaction_type: str | None = None,
        spending_category: str | None = None,
        payment_channel: str | None = None,
    ):
        self._validate_pagination(limit, offset)
        if self.account_repository.get_account(account_id) is None:
            raise AccountNotFoundError(f"Account {account_id} was not found")
        self._validate_filters(transaction_type, spending_category, payment_channel)
        return self.transaction_repository.get_account_transactions(
            account_id,
            limit=limit,
            offset=offset,
            transaction_type=transaction_type,
            spending_category=spending_category,
            payment_channel=payment_channel,
        )

    def get_customer_transactions(
        self,
        customer_id: int,
        limit: int | None = None,
        offset: int = 0,
        transaction_type: str | None = None,
        spending_category: str | None = None,
        payment_channel: str | None = None,
    ):
        self._validate_pagination(limit, offset)
        if self.customer_repository.get_customer(customer_id) is None:
            raise CustomerNotFoundError(f"Customer {customer_id} was not found")
        self._validate_filters(transaction_type, spending_category, payment_channel)
        return self.transaction_repository.get_customer_transactions(
            customer_id,
            limit=limit,
            offset=offset,
            transaction_type=transaction_type,
            spending_category=spending_category,
            payment_channel=payment_channel,
        )

    def get_transaction_summary(
        self,
        start_date: date,
        end_date: date,
        transaction_type: str | None = None,
    ) -> dict:
        if start_date > end_date:
            raise ValidationError("start_date must not be after end_date")
        if transaction_type is not None:
            transaction_type = transaction_type.strip().capitalize()
            if transaction_type not in {"Debit", "Credit"}:
                raise ValidationError("transaction_type must be Debit or Credit")
        transactions = self.transaction_repository.get_transactions_by_date_range(
            start_date, end_date, transaction_type=transaction_type
        )
        total_transaction_amount = sum(
            (transaction.transaction_amount for transaction in transactions),
            Decimal("0.00"),
        )
        by_type = {
            transaction_kind: {
                "transaction_count": sum(
                    transaction.transaction_type == transaction_kind
                    for transaction in transactions
                ),
                "total_transaction_amount": sum(
                    (
                        transaction.transaction_amount
                        for transaction in transactions
                        if transaction.transaction_type == transaction_kind
                    ),
                    Decimal("0.00"),
                ),
            }
            for transaction_kind in ("Debit", "Credit")
        }
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "transaction_type": transaction_type,
            "transaction_count": len(transactions),
            "total_transaction_amount": total_transaction_amount,
            "by_transaction_type": by_type,
        }

    @staticmethod
    def _validate_filters(*filters: str | None) -> None:
        if any(value is not None and not value.strip() for value in filters):
            raise ValidationError("transaction filters must not be blank")

    @staticmethod
    def _validate_pagination(limit: int | None, offset: int) -> None:
        if limit is not None and limit <= 0:
            raise ValidationError("limit must be greater than zero")
        if offset < 0:
            raise ValidationError("offset must not be negative")