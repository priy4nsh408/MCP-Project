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
        self, account_id: int, limit: int | None = None, offset: int = 0
    ):
        self._validate_pagination(limit, offset)
        if self.account_repository.get_account(account_id) is None:
            raise AccountNotFoundError(f"Account {account_id} was not found")
        return self.transaction_repository.get_account_transactions(
            account_id, limit=limit, offset=offset
        )

    def get_customer_transactions(
        self, customer_id: int, limit: int | None = None, offset: int = 0
    ):
        self._validate_pagination(limit, offset)
        if self.customer_repository.get_customer(customer_id) is None:
            raise CustomerNotFoundError(f"Customer {customer_id} was not found")
        return self.transaction_repository.get_customer_transactions(
            customer_id, limit=limit, offset=offset
        )

    @staticmethod
    def _validate_pagination(limit: int | None, offset: int) -> None:
        if limit is not None and limit <= 0:
            raise ValidationError("limit must be greater than zero")
        if offset < 0:
            raise ValidationError("offset must not be negative")