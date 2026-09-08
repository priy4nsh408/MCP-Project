from decimal import Decimal

from repositories.account_repository import AccountRepository
from repositories.customer_repository import CustomerRepository
from repositories.transaction_repository import TransactionRepository

from .dtos import CustomerSummary
from .errors import CustomerNotFoundError, ValidationError
from .totals import summarize_transactions


class CustomerService:
    def __init__(
        self,
        customer_repository: CustomerRepository,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
    ) -> None:
        self.customer_repository = customer_repository
        self.account_repository = account_repository
        self.transaction_repository = transaction_repository

    def get_customer(self, customer_id: int):
        customer = self.customer_repository.get_customer(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"Customer {customer_id} was not found")
        return customer

    def find_customers_by_name(self, name: str):
        if not name or not name.strip():
            raise ValidationError("customer name must not be blank")
        return self.customer_repository.search_customers(name=name.strip())

    def get_customer_accounts(self, customer_id: int):
        self.get_customer(customer_id)
        return self.account_repository.get_customer_accounts(customer_id)

    def get_customer_summary(self, customer_id: int) -> CustomerSummary:
        customer = self.get_customer(customer_id)
        accounts = self.account_repository.get_customer_accounts(customer_id)
        transactions = self.transaction_repository.get_customer_transactions(customer_id)
        total_balance = sum(
            (account.account_balance for account in accounts), Decimal("0.00")
        )
        return CustomerSummary(
            customer_id=customer.customer_id,
            customer_name=customer.customer_name,
            branch=customer.branch,
            account_count=len(accounts),
            total_balance=total_balance,
            transaction_summary=summarize_transactions(transactions),
        )

    @staticmethod
    def validate_pagination(limit: int | None, offset: int) -> None:
        if limit is not None and limit <= 0:
            raise ValidationError("limit must be greater than zero")
        if offset < 0:
            raise ValidationError("offset must not be negative")