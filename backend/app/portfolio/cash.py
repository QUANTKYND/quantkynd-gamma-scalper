from decimal import Decimal


def cash_balance(changes: list[Decimal] | tuple[Decimal, ...]) -> Decimal:
    return sum(changes, start=Decimal("0.00"))
