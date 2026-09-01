class SnapshotError(ValueError):
    """Snapshot creation or verification failed."""


class ReconciliationError(ValueError):
    """Reported evidence or reconciliation parameters are invalid."""
