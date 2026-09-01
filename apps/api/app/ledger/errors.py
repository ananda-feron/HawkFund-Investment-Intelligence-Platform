class LedgerError(ValueError):
    """Base class for rejected ledger commands."""


class TransactionValidationError(LedgerError):
    """The command violates the accepted transaction contract."""


class OpeningBalanceError(LedgerError):
    """An opening fact is not first or unique in its ledger scope."""


class ReversalError(LedgerError):
    """A reversal target is missing, invalid, or already reversed."""
