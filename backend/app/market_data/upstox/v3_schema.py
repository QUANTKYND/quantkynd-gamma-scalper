from pathlib import Path


UPSTOX_V3_SCHEMA_ID = "upstox-market-data-feed-v3"
UPSTOX_V3_SCHEMA_SHA256 = "ded335a0c7d2054011c2c0e06f276007a3186d1e212268d85d665788e42916c4"
UPSTOX_V3_PROTO_PATH = Path(__file__).with_name("proto") / "MarketDataFeed.proto"
UPSTOX_V3_MAX_FEEDS = 5000
UPSTOX_V3_MAX_DEPTH_LEVELS = 30
UPSTOX_V3_MAX_STATUS_SEGMENTS = 256

UNADOPTED_SCHEMA_PATHS = tuple(
    sorted(
        (
            "FirstLevelWithGreeks.iv",
            "FirstLevelWithGreeks.optionGreeks.delta",
            "FirstLevelWithGreeks.optionGreeks.gamma",
            "FirstLevelWithGreeks.optionGreeks.rho",
            "FirstLevelWithGreeks.optionGreeks.theta",
            "FirstLevelWithGreeks.optionGreeks.vega",
            "IndexFullFeed.marketOHLC.ohlc",
            "MarketFullFeed.atp",
            "MarketFullFeed.iv",
            "MarketFullFeed.marketLevel.bidAskQuote[1:]",
            "MarketFullFeed.marketOHLC.ohlc",
            "MarketFullFeed.optionGreeks.delta",
            "MarketFullFeed.optionGreeks.gamma",
            "MarketFullFeed.optionGreeks.rho",
            "MarketFullFeed.optionGreeks.theta",
            "MarketFullFeed.optionGreeks.vega",
            "MarketFullFeed.tbq",
            "MarketFullFeed.tsq",
            "OHLC.close",
            "OHLC.high",
            "OHLC.interval",
            "OHLC.low",
            "OHLC.open",
            "OHLC.ts",
            "OHLC.vol",
        )
    )
)
