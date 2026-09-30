from argparse import ArgumentParser
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import delete

from .connection import create_schema, session_factory
from .models import Account, Customer, Transaction


EXPECTED_COLUMNS = {
    "customers": {"Customer ID", "Customer Name", "Branch"},
    "accounts": {"Customer ID", "Account ID", "Account Type", "Account Balance"},
    "transactions": {
        "Transaction ID",
        "Account ID",
        "Transaction Date",
        "Spending Category",
        "Payment Channel",
        "Transaction Type",
        "Transaction Amount",
    },
}

SHEET_TABLES = {
    "Sheet01": "customers",
    "Sheet02": "accounts",
    "Sheet3": "transactions",
}


def _read_sheet(path: Path, sheet_name: str, expected_columns: set[str]) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet_name, header=1)
    frame.columns = [str(column).strip() for column in frame.columns]
    actual_columns = set(frame.columns)
    if actual_columns != expected_columns:
        raise ValueError(
            f"Unexpected columns in {sheet_name}: "
            f"expected {sorted(expected_columns)}, got {sorted(actual_columns)}"
        )
    if frame.isna().any().any():
        raise ValueError(f"Missing values found in {sheet_name}")
    return frame


def _integer(value: object, field_name: str) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid integer for {field_name}: {value!r}") from error
    if converted != value:
        raise ValueError(f"Non-integral value for {field_name}: {value!r}")
    return converted


def _money(value: object, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"Invalid amount for {field_name}: {value!r}") from error
    if amount <= 0 and field_name == "Transaction Amount":
        raise ValueError(f"Transaction amount must be positive: {value!r}")
    if amount < 0:
        raise ValueError(f"Amount must not be negative: {value!r}")
    return amount


def import_workbook(workbook_path: Path) -> tuple[int, int, int]:
    customers = _read_sheet(
        workbook_path, "Sheet01", EXPECTED_COLUMNS[SHEET_TABLES["Sheet01"]]
    )
    accounts = _read_sheet(
        workbook_path, "Sheet02", EXPECTED_COLUMNS[SHEET_TABLES["Sheet02"]]
    )
    transactions = _read_sheet(
        workbook_path, "Sheet3", EXPECTED_COLUMNS[SHEET_TABLES["Sheet3"]]
    )

    create_schema()
    with session_factory.begin() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Account))
        session.execute(delete(Customer))

        session.add_all(
            Customer(
                customer_id=_integer(row["Customer ID"], "Customer ID"),
                customer_name=str(row["Customer Name"]).strip(),
                branch=str(row["Branch"]).strip(),
            )
            for _, row in customers.iterrows()
        )
        session.add_all(
            Account(
                account_id=_integer(row["Account ID"], "Account ID"),
                customer_id=_integer(row["Customer ID"], "Customer ID"),
                account_type=str(row["Account Type"]).strip(),
                account_balance=_money(row["Account Balance"], "Account Balance"),
            )
            for _, row in accounts.iterrows()
        )
        session.add_all(
            Transaction(
                transaction_id=_integer(row["Transaction ID"], "Transaction ID"),
                account_id=_integer(row["Account ID"], "Account ID"),
                transaction_date=pd.Timestamp(row["Transaction Date"]).date(),
                spending_category=str(row["Spending Category"]).strip(),
                payment_channel=str(row["Payment Channel"]).strip(),
                transaction_type=str(row["Transaction Type"]).strip(),
                transaction_amount=_money(
                    row["Transaction Amount"], "Transaction Amount"
                ),
            )
            for _, row in transactions.iterrows()
        )

    return len(customers), len(accounts), len(transactions)


def main() -> None:
    parser = ArgumentParser(
        description="Import each banking Excel sheet into its PostgreSQL table."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("dataset/banking_dataset_final.xlsx"),
    )
    args = parser.parse_args()
    counts = import_workbook(args.workbook)
    print(
        f"Imported {counts[0]} customers, {counts[1]} accounts, "
        f"and {counts[2]} transactions."
    )


if __name__ == "__main__":
    main()