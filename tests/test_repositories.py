from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.models import Account, Customer, Transaction
from repositories.account_repository import AccountRepository
from repositories.customer_repository import CustomerRepository
from repositories.transaction_repository import TransactionRepository


def build_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Customer(customer_id=1, customer_name="Test Customer", branch="Delhi"))
    session.add(
        Account(
            account_id=10,
            customer_id=1,
            account_type="Savings",
            account_balance=Decimal("100.00"),
        )
    )
    session.add(
        Transaction(
            transaction_id=100,
            account_id=10,
            transaction_date=date(2025, 1, 1),
            spending_category="Groceries",
            payment_channel="UPI",
            transaction_type="Debit",
            transaction_amount=Decimal("25.50"),
        )
    )
    session.commit()
    return session


def test_repositories_read_related_records() -> None:
    session = build_session()

    customer_repository = CustomerRepository(session)
    account_repository = AccountRepository(session)
    transaction_repository = TransactionRepository(session)

    assert customer_repository.get_customer(1).customer_name == "Test Customer"
    assert [account.account_id for account in account_repository.get_customer_accounts(1)] == [10]
    assert [
        transaction.transaction_id
        for transaction in transaction_repository.get_account_transactions(10)
    ] == [100]
    assert [
        transaction.transaction_id
        for transaction in transaction_repository.get_customer_transactions(1)
    ] == [100]

    session.close()