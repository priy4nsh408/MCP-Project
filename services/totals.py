from collections.abc import Iterable
from decimal import Decimal

from database.models import Transaction

from .dtos import SpendingCategoryTotal, TransactionSummary


def summarize_transactions(transactions: Iterable[Transaction]) -> TransactionSummary:
    transaction_list = list(transactions)
    debits = [
        transaction
        for transaction in transaction_list
        if transaction.transaction_type == "Debit"
    ]
    credits = [
        transaction
        for transaction in transaction_list
        if transaction.transaction_type == "Credit"
    ]
    debit_total = sum(
        (transaction.transaction_amount for transaction in debits), Decimal("0.00")
    )
    credit_total = sum(
        (transaction.transaction_amount for transaction in credits), Decimal("0.00")
    )
    total_amount = debit_total + credit_total
    average_amount = (
        total_amount / len(transaction_list)
        if transaction_list
        else Decimal("0.00")
    )
    return TransactionSummary(
        transaction_count=len(transaction_list),
        debit_count=len(debits),
        credit_count=len(credits),
        debit_total=debit_total,
        credit_total=credit_total,
        average_amount=average_amount.quantize(Decimal("0.01")),
    )


def top_debit_categories(
    transactions: Iterable[Transaction], limit: int
) -> list[SpendingCategoryTotal]:
    totals: dict[str, Decimal] = {}
    for transaction in transactions:
        if transaction.transaction_type == "Debit":
            totals[transaction.spending_category] = (
                totals.get(transaction.spending_category, Decimal("0.00"))
                + transaction.transaction_amount
            )
    return [
        SpendingCategoryTotal(category=category, debit_total=total)
        for category, total in sorted(
            totals.items(), key=lambda item: (-item[1], item[0])
        )[:limit]
    ]