from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.models import Account, Customer, Transaction
from repositories.account_repository import AccountRepository
from repositories.customer_repository import CustomerRepository
from repositories.transaction_repository import TransactionRepository
from services.account_service import AccountService
from services.customer_service import CustomerService
from services.errors import AccountNotFoundError, ValidationError
from services.transaction_service import TransactionService


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


def build_services():
    session = build_session()
    customer_repository = CustomerRepository(session)
    account_repository = AccountRepository(session)
    transaction_repository = TransactionRepository(session)
    return (
        session,
        CustomerService(
            customer_repository, account_repository, transaction_repository
        ),
        AccountService(account_repository, transaction_repository),
        TransactionService(
            transaction_repository, account_repository, customer_repository
        ),
    )


def test_account_service_calculates_spending_and_summary() -> None:
    session, customer_service, account_service, transaction_service = build_services()

    assert account_service.calculate_spending(10) == Decimal("25.50")
    summary = account_service.get_account_summary(10)
    assert summary.transaction_summary.transaction_count == 1
    assert summary.transaction_summary.debit_total == Decimal("25.50")
    assert summary.top_spending_categories[0].category == "Groceries"
    assert customer_service.get_customer_summary(1).account_count == 1
    assert len(transaction_service.get_customer_transactions(1)) == 1
    summary = transaction_service.get_transaction_summary(
        date(2025, 1, 1), date(2025, 1, 1)
    )
    assert summary["total_transaction_amount"] == Decimal("25.50")

    session.close()


def test_services_raise_domain_errors_and_validate_pagination() -> None:
    session, _, account_service, transaction_service = build_services()

    with pytest.raises(AccountNotFoundError):
        account_service.get_account(999)
    with pytest.raises(ValidationError):
        account_service.get_account_transactions(10, limit=0)
    with pytest.raises(ValidationError):
        transaction_service.get_customer_transactions(1, offset=-1)
    with pytest.raises(ValidationError):
        transaction_service.get_transaction_summary(date(2025, 2, 1), date(2025, 1, 1))

    session.close()