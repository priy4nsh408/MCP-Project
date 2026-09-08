from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Account


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: int) -> Account | None:
        return self.session.get(Account, account_id)

    def get_customer_accounts(self, customer_id: int) -> list[Account]:
        statement = (
            select(Account)
            .where(Account.customer_id == customer_id)
            .order_by(Account.account_id)
        )
        return list(self.session.scalars(statement))

    def search_accounts(
        self,
        customer_id: int | None = None,
        account_type: str | None = None,
        limit: int | None = None,
    ) -> list[Account]:
        statement = select(Account).order_by(Account.account_id)
        if customer_id is not None:
            statement = statement.where(Account.customer_id == customer_id)
        if account_type:
            statement = statement.where(Account.account_type == account_type)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))