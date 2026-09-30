import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .base import Base


load_dotenv()


def _database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if configured_url:
        return configured_url

    if not os.getenv("POSTGRES_PASSWORD"):
        project_root = Path(__file__).resolve().parent.parent
        return f"sqlite:///{project_root / 'database' / 'banking.db'}"

    return (
        "postgresql+psycopg://"
        f"{os.getenv('POSTGRES_USER', 'postgres')}:{os.getenv('POSTGRES_PASSWORD', '')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB', 'banking')}"
    )


DATABASE_URL = _database_url()

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_schema() -> None:
    from . import models

    del models
    Base.metadata.create_all(engine)