from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .base import Base


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "banking.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, future=True)
session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection: sqlite3.Connection, connection_record: object) -> None:
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_schema() -> None:
    from . import models

    del models
    Base.metadata.create_all(engine)