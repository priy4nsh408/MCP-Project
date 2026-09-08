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
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.transaction_date, Transaction.transaction_id)
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def get_customer_transactions(
        self,
        customer_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .join(Account, Account.account_id == Transaction.account_id)
            .where(Account.customer_id == customer_id)
            .order_by(Transaction.transaction_date, Transaction.transaction_id)
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))