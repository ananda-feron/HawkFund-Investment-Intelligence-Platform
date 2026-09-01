class MarketDataError(ValueError):
    pass


class InvalidPriceObservation(MarketDataError):
    pass


class UnknownSecurityIdentifier(MarketDataError):
    pass


class MissingPriceError(MarketDataError):
    pass
