import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.models import Account, AdminDetail, AuditLog, Customer, Transaction
from services.write_service import WriteService
from servers import write_server


def build_write_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            AdminDetail(email="admin@example.com", password="admin-password")
        )
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
    return factory


def call_tool(name: str, arguments: dict):
    arguments.setdefault("email", "admin@example.com")
    arguments.setdefault("password", "admin-password")
    return asyncio.run(write_server.handle_call_tool(name, arguments))


def test_write_server_authentication_authorization_and_confirmation(monkeypatch) -> None:
    factory = build_write_session_factory()
    monkeypatch.setattr(write_server, "write_service", WriteService(factory))
    monkeypatch.setenv("BANKING_WRITE_ROLE", "writer")

    created = call_tool(
        "create_transaction",
        {
            "account_id": 10,
            "transaction_date": "2025-02-01",
            "spending_category": "Dining",
            "payment_channel": "UPI",
            "transaction_type": "Debit",
            "transaction_amount": 10.25,
        },
    )
    assert created["transaction_id"] == 101

    delete_denied = call_tool(
        "delete_transaction", {"transaction_id": 101, "confirmation": "CONFIRM_DELETE"}
    )
    assert delete_denied.structuredContent["error"]["code"] == "UNAUTHORIZED_OPERATION"

    monkeypatch.setenv("BANKING_WRITE_ROLE", "admin")
    no_confirmation = call_tool(
        "delete_transaction", {"transaction_id": 101, "confirmation": "no"}
    )
    assert no_confirmation.structuredContent["error"]["code"] == "CONFIRMATION_REQUIRED"

    deleted = call_tool(
        "delete_transaction", {"transaction_id": 101, "confirmation": "CONFIRM_DELETE"}
    )
    assert deleted["deleted"] is True

    with factory() as session:
        audit_logs = session.scalars(select(AuditLog)).all()
        assert [audit.status for audit in audit_logs].count("SUCCESS") == 2


def test_write_server_authentication_and_rollback(monkeypatch) -> None:
    factory = build_write_session_factory()
    monkeypatch.setattr(write_server, "write_service", WriteService(factory))
    monkeypatch.setenv("BANKING_WRITE_ROLE", "writer")

    unauthenticated_arguments = {
        "account_id": 10,
        "transaction_date": "2025-02-01",
        "spending_category": "Dining",
        "payment_channel": "UPI",
        "transaction_type": "Debit",
        "transaction_amount": 10.25,
        "email": "admin@example.com",
    }
    unauthenticated_arguments["password"] = "wrong-password"
    unauthenticated = call_tool(
        "create_transaction",
        unauthenticated_arguments,
    )
    assert unauthenticated.structuredContent["error"]["code"] == "AUTHENTICATION_FAILED"

    failed = call_tool(
        "create_transaction",
        {
            "account_id": 999,
            "transaction_date": "2025-02-01",
            "spending_category": "Dining",
            "payment_channel": "UPI",
            "transaction_type": "Debit",
            "transaction_amount": 10.25,
        },
    )
    assert failed.structuredContent["error"]["code"] == "ACCOUNT_NOT_FOUND"

    with factory() as session:
        assert session.scalar(select(Transaction).where(Transaction.transaction_id == 101)) is None
        failed_audits = session.scalars(
            select(AuditLog).where(AuditLog.status == "FAILED")
        ).all()
        assert len(failed_audits) == 1