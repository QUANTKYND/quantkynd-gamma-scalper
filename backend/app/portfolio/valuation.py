from decimal import Decimal

from app.portfolio.positions import InstrumentPosition


def portfolio_market_value(positions: list[InstrumentPosition] | tuple[InstrumentPosition, ...]) -> Decimal:
    return sum((position.market_value for position in positions), start=Decimal("0.00"))
