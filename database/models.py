from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class AdminDetail(Base):
    __tablename__ = "Admin_details"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    branch: Mapped[str] = mapped_column(String(100), nullable=False)

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('Salary', 'Current', 'Savings')",
            name="ck_accounts_account_type",
        ),
        CheckConstraint("account_balance >= 0", name="ck_accounts_balance_nonnegative"),
        Index("ix_accounts_customer_id", "customer_id"),
    )

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False
    )
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    account_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('Debit', 'Credit')",
            name="ck_transactions_type",
        ),
        CheckConstraint(
            "transaction_amount > 0",
            name="ck_transactions_amount_positive",
        ),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_date", "transaction_date"),
        Index("ix_transactions_type", "transaction_type"),
        Index("ix_transactions_category", "spending_category"),
    )

    transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    spending_category: Mapped[str] = mapped_column(String(100), nullable=False)
    payment_channel: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    account: Mapped[Account] = relationship(back_populates="transactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)