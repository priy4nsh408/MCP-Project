import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import MetaData, Table, inspect, select
from services.errors import AuthenticationError


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: str


def _password_matches(stored_password: str, supplied_password: str) -> bool:
    if stored_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations_text, salt, expected = stored_password.split("$", 3)
            derived = hashlib.pbkdf2_hmac(
                "sha256",
                supplied_password.encode(),
                salt.encode(),
                int(iterations_text),
            ).hex()
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(derived, expected)
    return hmac.compare_digest(stored_password, supplied_password)


def authenticate(
    email: str | None, password: str | None, session_factory: Any
) -> Principal:
    if not email or not password:
        raise AuthenticationError("admin email and password are required")

    with session_factory() as session:
        admin_columns = {
            column["name"]
            for column in inspect(session.bind).get_columns("Admin_details")
        }
        password_column = (
            "password" if "password" in admin_columns else "password_hash"
        )
        if "email" not in admin_columns or password_column not in admin_columns:
            raise AuthenticationError("admin credentials are not configured")

        admin_table = Table(
            "Admin_details", MetaData(), autoload_with=session.bind
        )
        admin = session.execute(
            select(admin_table.c.email, admin_table.c[password_column]).where(
                admin_table.c.email == email.strip()
            )
        ).one_or_none()
        if admin is None or not _password_matches(admin[1], password):
            raise AuthenticationError("write authentication failed")

    actor_id = email.strip()
    role = os.environ.get("BANKING_WRITE_ROLE", "").strip()
    if not actor_id or not role:
        raise AuthenticationError(
            "BANKING_WRITE_ROLE must be configured"
        )
    return Principal(actor_id=actor_id, role=role)