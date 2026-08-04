from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pandas as pd

from app.instruments.models import InstrumentDefinition as DomainInstrument
from app.market_data.models import FreshnessState, LiveQuoteState
from app.schemas.instruments import InstrumentDefinition
from app.schemas.rv import RVFeatureResponse, RVLatestResponse, RVLiveOverlayMetadata
from app.services.rv_service import RVResearchSnapshot, RVService


class RVLiveOverlayBuilder:
    def latest(
        self,
        finalized_snapshot: RVResearchSnapshot,
        instrument: DomainInstrument,
        quote: LiveQuoteState | None,
        freshness: FreshnessState,
    ) -> RVLatestResponse:
        snapshot, provisional = self._overlay_snapshot(finalized_snapshot, quote)
        response = RVService(symbol=snapshot.symbol, snapshot=snapshot).latest()
        return response.model_copy(
            update={
                "instrument": InstrumentDefinition.model_validate(asdict(instrument)),
                "finalized_as_of": finalized_snapshot.dataset_metadata.end_date,
                "live": self._metadata(instrument.instrument_key, quote, freshness, provisional),
            }
        )

    def feature_series(
        self,
        finalized_snapshot: RVResearchSnapshot,
        instrument: DomainInstrument,
        quote: LiveQuoteState | None,
        freshness: FreshnessState,
        limit: int,
    ) -> RVFeatureResponse:
        snapshot, provisional = self._overlay_snapshot(finalized_snapshot, quote)
        response = RVService(symbol=snapshot.symbol, snapshot=snapshot).feature_series(limit=limit)
        points = response.points
        if provisional and points:
            points = [*points[:-1], points[-1].model_copy(update={"is_provisional": True})]
        return response.model_copy(
            update={
                "points": points,
                "instrument": InstrumentDefinition.model_validate(asdict(instrument)),
                "finalized_as_of": finalized_snapshot.dataset_metadata.end_date,
                "live": self._metadata(instrument.instrument_key, quote, freshness, provisional),
            }
        )

    def _overlay_snapshot(self, finalized: RVResearchSnapshot, quote: LiveQuoteState | None) -> tuple[RVResearchSnapshot, bool]:
        if quote is None or quote.ltp <= 0:
            return finalized, False
        quote_date = quote.last_trade_at.astimezone(_india_timezone()).date()
        if quote_date <= finalized.dataset_metadata.end_date:
            return finalized, False
        prices = pd.concat(
            [finalized.prices, pd.Series([quote.ltp], index=[pd.Timestamp(quote_date)], name="price")]
        )
        from app.quant.rv_features import build_rv_feature_frame

        return RVResearchSnapshot(
            symbol=finalized.symbol,
            prices=prices,
            features=build_rv_feature_frame(prices),
            backtest=finalized.backtest,
            estimator_metadata=finalized.estimator_metadata,
            dataset_metadata=finalized.dataset_metadata,
        ), True

    def _metadata(
        self,
        instrument_key: str,
        quote: LiveQuoteState | None,
        freshness: FreshnessState,
        provisional: bool,
    ) -> RVLiveOverlayMetadata:
        return RVLiveOverlayMetadata(
            instrument_key=instrument_key,
            price_source="live_ltp" if provisional else "final_close",
            is_provisional=provisional,
            freshness=freshness,
            market_status=quote.market_status if quote else None,
            previous_close=quote.previous_close if quote else None,
            last_trade_at=quote.last_trade_at if quote else None,
            received_at=quote.received_at if quote else None,
        )


def _india_timezone():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Kolkata")
