import pandas as pd
from pandas.testing import assert_frame_equal

from app.quant.rv_features import build_rv_feature_frame, rv_lag_features


def _prices(n: int = 120) -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=n)
    returns = pd.Series(
        [0.001 + ((i % 11) - 5) * 0.0007 for i in range(n)],
        index=index,
    )
    return 100 * (1 + returns).cumprod()


def test_feature_frame_has_expected_columns():
    features = build_rv_feature_frame(_prices())

    assert list(features.columns) == [
        "rv_1d",
        "rv_5d",
        "rv_21d",
        "rv_63d",
        "rv_ratio_5_21",
        "rv_z_21",
        "rv_regime",
    ]


def test_feature_frame_alignment_matches_prices():
    prices = _prices()

    features = build_rv_feature_frame(prices)

    assert features.index.equals(prices.index)
    assert len(features) == len(prices)


def test_feature_frame_uses_no_future_prices():
    prices = _prices()
    shocked = prices.copy()
    shocked.iloc[80:] = shocked.iloc[80:] * 1.5

    before = build_rv_feature_frame(prices)
    after = build_rv_feature_frame(shocked)

    assert_frame_equal(before.iloc[:80], after.iloc[:80])


def test_feature_warmup_nulls_are_explicit():
    features = build_rv_feature_frame(_prices())

    assert features["rv_63d"].iloc[:64].isna().all()
    assert features["rv_63d"].iloc[64:].notna().all()
    assert features["rv_regime"].iloc[:64].isna().all()


def test_lag_features_shift_rv_values():
    rv = pd.Series([0.1, 0.2, 0.3, 0.4])

    lags = rv_lag_features(rv, lags=(1, 2))

    assert lags["rv_lag_1"].iloc[0] != lags["rv_lag_1"].iloc[0]
    assert lags["rv_lag_1"].iloc[1:].tolist() == [0.1, 0.2, 0.3]
    assert lags["rv_lag_2"].iloc[:2].isna().all()
    assert lags["rv_lag_2"].iloc[2:].tolist() == [0.1, 0.2]
