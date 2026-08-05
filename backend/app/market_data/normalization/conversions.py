from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal


INT64_MAX = 2**63 - 1
SAFE_INTEGER_MAX = 2**53
EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)


def provider_double_to_price(value: float) -> Decimal:
    if not isinstance(value, float):
        raise TypeError("provider price must be a protobuf double")
    if not math.isfinite(value):
        raise ValueError("nonfinite_price")
    decimal = Decimal(str(value))
    if decimal.is_zero():
        return Decimal(0)
    if decimal < 0:
        raise ValueError("negative_price")
    return decimal


def reported_quantity(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= INT64_MAX:
        raise ValueError("invalid_quantity")
    return value


def reported_open_interest(value: float) -> int:
    if not isinstance(value, float) or not math.isfinite(value):
        raise ValueError("unsafe_open_interest")
    if value < 0 or value > SAFE_INTEGER_MAX or value > INT64_MAX:
        raise ValueError("unsafe_open_interest")
    if not value.is_integer():
        raise ValueError("fractional_open_interest")
    return int(value)


def epoch_milliseconds(value: int, *, zero_is_none: bool) -> datetime | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid_timestamp")
    if value == 0 and zero_is_none:
        return None
    if value == 0:
        raise ValueError("invalid_timestamp")
    seconds, milliseconds = divmod(value, 1000)
    try:
        return EPOCH_UTC + timedelta(seconds=seconds, milliseconds=milliseconds)
    except OverflowError as error:
        raise ValueError("invalid_timestamp") from error
