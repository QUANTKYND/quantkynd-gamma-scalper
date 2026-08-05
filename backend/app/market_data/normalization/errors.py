class MarketNormalizationError(ValueError):
    code = "market_normalization_error"


class RawFrameValidationError(MarketNormalizationError):
    code = "invalid_raw_frame"


class ConflictingRawIdentityError(MarketNormalizationError):
    code = "conflicting_raw_identity"


class FrameDecodeError(MarketNormalizationError):
    def __init__(self, code: str, response_type_numeric: int | None = None) -> None:
        self.code = code
        self.response_type_numeric = response_type_numeric
        super().__init__(code)


class SubjectResolutionError(MarketNormalizationError):
    def __init__(self, code: str, provider_contract_key: str) -> None:
        self.code = code
        self.provider_contract_key = provider_contract_key
        super().__init__(f"{code}: {provider_contract_key}")
