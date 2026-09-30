from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Account, Transaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_transaction(self, transaction_id: int) -> Transaction | None:
        return self.session.get(Transaction, transaction_id)

    def get_account_transactions(
        self,
        account_id: int,
        limit: int | None = None,
        offset: int = 0,
        transaction_type: str | None = None,
        spending_category: str | None = None,
        payment_channel: str | None = None,
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.transaction_date, Transaction.transaction_id)
            .offset(offset)
        )
        if transaction_type:
            statement = statement.where(Transaction.transaction_type == transaction_type)
        if spending_category:
            statement = statement.where(
                Transaction.spending_category == spending_category
            )
        if payment_channel:
            statement = statement.where(Transaction.payment_channel == payment_channel)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def get_customer_transactions(
        self,
        customer_id: int,
        limit: int | None = None,
        offset: int = 0,
        transaction_type: str | None = None,
        spending_category: str | None = None,
        payment_channel: str | None = None,
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .join(Account, Account.account_id == Transaction.account_id)
            .where(Account.customer_id == customer_id)
            .order_by(Transaction.transaction_date, Transaction.transaction_id)
            .offset(offset)
        )
        if transaction_type:
            statement = statement.where(Transaction.transaction_type == transaction_type)
        if spending_category:
            statement = statement.where(
                Transaction.spending_category == spending_category
            )
        if payment_channel:
            statement = statement.where(Transaction.payment_channel == payment_channel)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def get_transactions_by_date_range(
        self, start_date, end_date, transaction_type: str | None = None
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .where(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
            .order_by(Transaction.transaction_date, Transaction.transaction_id)
        )
        if transaction_type:
            statement = statement.where(Transaction.transaction_type == transaction_type)
        return list(self.session.scalars(statement))