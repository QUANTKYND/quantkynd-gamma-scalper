from enum import StrEnum


class RawCaptureBasis(StrEnum):
    LIVE_RECEIVED = "live_received"
    RECORDED_WITH_ORIGINAL_RECEIPT = "recorded_with_original_receipt"
    HISTORICAL_IMPORT = "historical_import"


class NormalizedAvailabilityBasis(StrEnum):
    RECEIVED = "received"
    HISTORICAL_IMPORT = "historical_import"


class MarketSubjectKind(StrEnum):
    UNDERLYING = "underlying"
    FUTURE = "future"
    OPTION = "option"


class FeedResponseType(StrEnum):
    INITIAL_FEED = "initial_feed"
    LIVE_FEED = "live_feed"
    MARKET_INFO = "market_info"


class ProviderRequestMode(StrEnum):
    LTPC = "ltpc"
    FULL_D5 = "full_d5"
    OPTION_GREEKS = "option_greeks"
    FULL_D30 = "full_d30"


class ProviderFeedUnion(StrEnum):
    LTPC = "ltpc"
    INDEX_FULL_FEED = "indexFF"
    MARKET_FULL_FEED = "marketFF"
    FIRST_LEVEL_WITH_GREEKS = "firstLevelWithGreeks"


class FrameNormalizationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class NormalizationFailureScope(StrEnum):
    FRAME = "frame"
    SUBJECT = "subject"
    SEGMENT = "segment"
    CONNECTION_LIFECYCLE = "connection_lifecycle"
    SUBSCRIPTION_LIFECYCLE = "subscription_lifecycle"
