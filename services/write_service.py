from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import sessionmaker

from audit.audit_logger import record_audit
from database.models import Account, Transaction
from security.authentication import Principal
from security.authorization import require_confirmation, require_write_permission

from .errors import (
    AccountNotFoundError,
    BankingError,
    DatabaseError,
    TransactionNotFoundError,
    ValidationError,
)


class WriteService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def create_transaction(
        self,
        principal: Principal,
        *,
        account_id: int,
        transaction_date: date,
        spending_category: str,
        payment_channel: str,
        transaction_type: str,
        transaction_amount: Decimal,
    ) -> dict[str, Any]:
        operation = "create_transaction"
        require_write_permission(principal, operation)
        self._validate_transaction_values(
            spending_category,
            payment_channel,
            transaction_type,
            transaction_amount,
        )
        try:
            with self.session_factory.begin() as session:
                if session.get(Account, account_id) is None:
                    raise AccountNotFoundError(f"Account {account_id} was not found")
                transaction = Transaction(
                    account_id=account_id,
                    transaction_date=transaction_date,
                    spending_category=spending_category.strip(),
                    payment_channel=payment_channel.strip(),
                    transaction_type=transaction_type,
                    transaction_amount=transaction_amount,
                )
                session.add(transaction)
                session.flush()
                result = self._transaction_dict(transaction)
                record_audit(
                    session,
                    actor_id=principal.actor_id,
                    operation=operation,
                    entity_type="transaction",
                    entity_id=transaction.transaction_id,
                    old_value=None,
                    new_value=result,
                    status="SUCCESS",
                )
                return result
        except BankingError as error:
            self._record_failure(principal, operation, account_id, error)
            raise
        except Exception as error:
            database_error = DatabaseError("transaction creation failed")
            self._record_failure(principal, operation, account_id, database_error)
            raise database_error from error

    def update_transaction(
        self,
        principal: Principal,
        *,
        transaction_id: int,
        transaction_date: date | None = None,
        spending_category: str | None = None,
        payment_channel: str | None = None,
        transaction_type: str | None = None,
        transaction_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        operation = "update_transaction"
        require_write_permission(principal, operation)
        if all(
            value is None
            for value in (
                transaction_date,
                spending_category,
                payment_channel,
                transaction_type,
                transaction_amount,
            )
        ):
            raise ValidationError("at least one transaction field must be supplied")
        if transaction_type is not None and transaction_type not in {"Debit", "Credit"}:
            raise ValidationError("transaction_type must be Debit or Credit")
        if transaction_amount is not None:
            self._validate_amount(transaction_amount)
        for value, field_name in (
            (spending_category, "spending_category"),
            (payment_channel, "payment_channel"),
        ):
            if value is not None and not value.strip():
                raise ValidationError(f"{field_name} must not be blank")

        try:
            with self.session_factory.begin() as session:
                transaction = session.get(Transaction, transaction_id)
                if transaction is None:
                    raise TransactionNotFoundError(
                        f"Transaction {transaction_id} was not found"
                    )
                old_value = self._transaction_dict(transaction)
                if transaction_date is not None:
                    transaction.transaction_date = transaction_date
                if spending_category is not None:
                    transaction.spending_category = spending_category.strip()
                if payment_channel is not None:
                    transaction.payment_channel = payment_channel.strip()
                if transaction_type is not None:
                    transaction.transaction_type = transaction_type
                if transaction_amount is not None:
                    transaction.transaction_amount = transaction_amount
                session.flush()
                result = self._transaction_dict(transaction)
                record_audit(
                    session,
                    actor_id=principal.actor_id,
                    operation=operation,
                    entity_type="transaction",
                    entity_id=transaction_id,
                    old_value=old_value,
                    new_value=result,
                    status="SUCCESS",
                )
                return result
        except BankingError as error:
            self._record_failure(principal, operation, transaction_id, error)
            raise
        except Exception as error:
            database_error = DatabaseError("transaction update failed")
            self._record_failure(principal, operation, transaction_id, database_error)
            raise database_error from error

    def delete_transaction(
        self, principal: Principal, *, transaction_id: int, confirmation: str | None
    ) -> dict[str, Any]:
        operation = "delete_transaction"
        require_write_permission(principal, operation)
        require_confirmation(confirmation)
        try:
            with self.session_factory.begin() as session:
                transaction = session.get(Transaction, transaction_id)
                if transaction is None:
                    raise TransactionNotFoundError(
                        f"Transaction {transaction_id} was not found"
                    )
                old_value = self._transaction_dict(transaction)
                session.delete(transaction)
                record_audit(
                    session,
                    actor_id=principal.actor_id,
                    operation=operation,
                    entity_type="transaction",
                    entity_id=transaction_id,
                    old_value=old_value,
                    new_value=None,
                    status="SUCCESS",
                )
                return {"transaction_id": transaction_id, "deleted": True}
        except BankingError as error:
            self._record_failure(principal, operation, transaction_id, error)
            raise
        except Exception as error:
            database_error = DatabaseError("transaction deletion failed")
            self._record_failure(principal, operation, transaction_id, database_error)
            raise database_error from error

    def _record_failure(
        self,
        principal: Principal,
        operation: str,
        entity_id: int,
        error: BankingError,
    ) -> None:
        try:
            with self.session_factory.begin() as session:
                record_audit(
                    session,
                    actor_id=principal.actor_id,
                    operation=operation,
                    entity_type="transaction",
                    entity_id=entity_id,
                    old_value=None,
                    new_value={"error_code": error.code},
                    status="FAILED",
                )
        except Exception:
            pass

    @staticmethod
    def _validate_transaction_values(
        spending_category: str,
        payment_channel: str,
        transaction_type: str,
        transaction_amount: Decimal,
    ) -> None:
        if not spending_category.strip() or not payment_channel.strip():
            raise ValidationError("category and payment channel must not be blank")
        if transaction_type not in {"Debit", "Credit"}:
            raise ValidationError("transaction_type must be Debit or Credit")
        WriteService._validate_amount(transaction_amount)

    @staticmethod
    def _validate_amount(amount: Decimal) -> None:
        try:
            if amount <= 0:
                raise ValidationError("transaction amount must be positive")
        except (InvalidOperation, TypeError) as error:
            raise ValidationError("transaction amount must be numeric") from error

    @staticmethod
    def _transaction_dict(transaction: Transaction) -> dict[str, Any]:
        return {
            "transaction_id": transaction.transaction_id,
            "account_id": transaction.account_id,
            "transaction_date": transaction.transaction_date.isoformat(),
            "spending_category": transaction.spending_category,
            "payment_channel": transaction.payment_channel,
            "transaction_type": transaction.transaction_type,
            "transaction_amount": format(transaction.transaction_amount, "f"),
        }