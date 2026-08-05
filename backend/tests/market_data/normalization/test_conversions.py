from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.market_data.normalization.conversions import (
    epoch_milliseconds,
    provider_double_to_price,
    reported_open_interest,
    reported_quantity,
)


def test_provider_double_conversion_preserves_zero_without_float() -> None:
    assert provider_double_to_price(-0.0) == Decimal(0)
    assert provider_double_to_price(123.45) == Decimal("123.45")
    assert isinstance(provider_double_to_price(123.45), Decimal)


@pytest.mark.parametrize("value,code", [(float("nan"), "nonfinite_price"), (float("inf"), "nonfinite_price"), (-0.1, "negative_price")])
def test_invalid_provider_prices_fail(value, code) -> None:
    with pytest.raises(ValueError, match=code):
        provider_double_to_price(value)


@pytest.mark.parametrize("value", [-1, 2**63, True])
def test_invalid_reported_quantity_fails(value) -> None:
    with pytest.raises(ValueError, match="invalid_quantity"):
        reported_quantity(value)


def test_open_interest_requires_safe_integral_double() -> None:
    assert reported_open_interest(0.0) == 0
    assert reported_open_interest(float(2**53)) == 2**53
    with pytest.raises(ValueError, match="fractional_open_interest"):
        reported_open_interest(1.5)
    with pytest.raises(ValueError, match="unsafe_open_interest"):
        reported_open_interest(float("nan"))
    with pytest.raises(ValueError, match="unsafe_open_interest"):
        reported_open_interest(float(2**53 + 2))


def test_epoch_milliseconds_use_integer_arithmetic() -> None:
    assert epoch_milliseconds(1_754_365_200_123, zero_is_none=False) == datetime(2025, 8, 5, 3, 40, 0, 123000, tzinfo=UTC)
    assert epoch_milliseconds(0, zero_is_none=True) is None
    with pytest.raises(ValueError, match="invalid_timestamp"):
        epoch_milliseconds(0, zero_is_none=False)
    with pytest.raises(ValueError, match="invalid_timestamp"):
        epoch_milliseconds(True, zero_is_none=False)
