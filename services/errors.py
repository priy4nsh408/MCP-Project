class BankingError(Exception):
    code = "BANKING_ERROR"


class CustomerNotFoundError(BankingError):
    code = "CUSTOMER_NOT_FOUND"


class AccountNotFoundError(BankingError):
    code = "ACCOUNT_NOT_FOUND"


class TransactionNotFoundError(BankingError):
    code = "TRANSACTION_NOT_FOUND"


class ValidationError(BankingError):
    code = "VALIDATION_ERROR"


class AuthenticationError(BankingError):
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(BankingError):
    code = "UNAUTHORIZED_OPERATION"


class ConfirmationRequiredError(BankingError):
    code = "CONFIRMATION_REQUIRED"


class DatabaseError(BankingError):
    code = "DATABASE_ERROR"