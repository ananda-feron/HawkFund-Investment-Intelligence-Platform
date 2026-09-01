from uuid import UUID


class PortfolioReconstructionError(ValueError):
    """Base class for deterministic reconstruction failures."""


class InvalidEngineInput(PortfolioReconstructionError):
    """Input records violate the reconstruction contract."""


class NegativeHoldingError(PortfolioReconstructionError):
    def __init__(
        self, transaction_id: UUID, message: str = "transaction creates a negative holding"
    ):
        self.transaction_id = transaction_id
        super().__init__(f"{message}: {transaction_id}")


class InvalidReversalError(PortfolioReconstructionError):
    """A reversal cannot be applied to the included ordered history."""


class NegativeCostBasisError(PortfolioReconstructionError):
    """A known position cost basis became negative."""
