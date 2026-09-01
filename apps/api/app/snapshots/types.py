from enum import Enum


class SnapshotStatus(str, Enum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"


class CostBasisPersistenceStatus(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class ReconciliationKind(str, Enum):
    CASH = "CASH"
    POSITION = "POSITION"


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    BREACH = "BREACH"
    UNAVAILABLE = "UNAVAILABLE"
