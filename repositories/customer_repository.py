from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Customer


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_customer(self, customer_id: int) -> Customer | None:
        return self.session.get(Customer, customer_id)

    def search_customers(
        self,
        name: str | None = None,
        branch: str | None = None,
        limit: int | None = None,
    ) -> list[Customer]:
        statement = select(Customer).order_by(Customer.customer_id)
        if name:
            statement = statement.where(Customer.customer_name.ilike(f"%{name}%"))
        if branch:
            statement = statement.where(Customer.branch == branch)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))