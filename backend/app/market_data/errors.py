class MarketDataError(RuntimeError):
    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AuthenticationRequired(MarketDataError):
    def __init__(self) -> None:
        super().__init__("Upstox authentication is required", code="authentication_required", status_code=401)


class InstrumentNotFound(MarketDataError):
    def __init__(self, instrument_key: str) -> None:
        super().__init__(f"Instrument was not found: {instrument_key}", code="instrument_not_found", status_code=404)


class ProviderUnavailable(MarketDataError):
    def __init__(self, message: str = "Upstox market data is unavailable") -> None:
        super().__init__(message, code="provider_unavailable", status_code=503)


class SubscriptionRejected(MarketDataError):
    def __init__(self, message: str = "Market-data subscription was rejected") -> None:
        super().__init__(message, code="subscription_rejected", status_code=429)


class InsufficientHistory(MarketDataError):
    def __init__(self) -> None:
        super().__init__("Insufficient finalized daily closes", code="insufficient_finalized_closes", status_code=422)
