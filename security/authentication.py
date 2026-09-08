import hmac
import os
from dataclasses import dataclass

from services.errors import AuthenticationError


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: str


def authenticate(token: str | None) -> Principal:
    expected_token = os.environ.get("BANKING_WRITE_TOKEN")
    if not expected_token:
        raise AuthenticationError(
            "BANKING_WRITE_TOKEN is not configured in the write-server process"
        )
    if not token or not hmac.compare_digest(token, expected_token):
        raise AuthenticationError("write authentication failed: invalid token")

    actor_id = os.environ.get("BANKING_WRITE_ACTOR")
    role = os.environ.get("BANKING_WRITE_ROLE")
    if not actor_id or not role:
        raise AuthenticationError(
            "BANKING_WRITE_ACTOR and BANKING_WRITE_ROLE must be configured"
        )
    return Principal(actor_id=actor_id, role=role)