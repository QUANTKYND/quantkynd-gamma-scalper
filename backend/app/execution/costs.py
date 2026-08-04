from decimal import ROUND_HALF_EVEN, Decimal


CURRENCY_QUANTUM = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_EVEN)
