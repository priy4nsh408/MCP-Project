from security.authentication import Principal
from services.errors import AuthorizationError, ConfirmationRequiredError


def require_write_permission(principal: Principal, operation: str) -> None:
    if operation in {"create_transaction", "update_transaction"}:
        allowed_roles = {"writer", "admin"}
    elif operation == "delete_transaction":
        allowed_roles = {"admin"}
    else:
        raise AuthorizationError(f"unknown write operation: {operation}")

    if principal.role not in allowed_roles:
        raise AuthorizationError(
            f"role {principal.role!r} cannot perform {operation}"
        )


def require_confirmation(confirmation: str | None) -> None:
    if confirmation != "CONFIRM_DELETE":
        raise ConfirmationRequiredError(
            "delete requires confirmation='CONFIRM_DELETE'"
        )