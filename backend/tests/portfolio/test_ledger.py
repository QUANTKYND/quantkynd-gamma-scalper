from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.execution.fills import simulate_fill
from app.execution.models import ExecutionCostParameters, OrderIntent
from app.portfolio.ledger import PortfolioLedger


ZERO_COSTS = ExecutionCostParameters(*(Decimal("0"),) * 4)


def fill(side: str, price: int, index: int, instrument: str = "OPTION"):
    intent = OrderIntent(
        f"i-{index}",
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        instrument,
        side,
        1,
        50,
        "test",
        "p-1",
        "policy",
    )
    return simulate_fill(intent, price, ZERO_COSTS)


def test_entry_exit_and_terminal_identity_reconcile() -> None:
    ledger = PortfolioLedger(Decimal("1000000"), datetime(2026, 1, 1, tzinfo=UTC), "p-1")
    ledger.record_fill(fill("buy", 100, 0), "option_entry", "p-1")
    assert ledger.cash == Decimal("995000.00")
    ledger.record_fill(fill("sell", 110, 1), "option_exit", "p-1")
    assert ledger.positions["OPTION"].quantity == 0
    assert ledger.positions["OPTION"].realized_pnl == Decimal("500.00")
    assert ledger.terminal_pnl() == Decimal("500.00")
    assert ledger.portfolio_value() - ledger.starting_nav == ledger.terminal_pnl()


def test_cost_is_deducted_once() -> None:
    costs = ExecutionCostParameters(Decimal("10"), Decimal("0"), Decimal("0"), Decimal("0"))
    ledger = PortfolioLedger(Decimal("1000"), datetime(2026, 1, 1, tzinfo=UTC), "p-1")
    intent = OrderIntent("i", datetime(2026, 1, 1, tzinfo=UTC), "FUT", "buy", 1, 1, "hedge", "p-1", "policy")
    ledger.record_fill(simulate_fill(intent, 100, costs), "futures_hedge_buy", "p-1")
    ledger.mark("FUT", 100)
    assert ledger.cash == Decimal("890.00")
    assert ledger.portfolio_value() == Decimal("990.00")
    assert ledger.terminal_pnl() == Decimal("-10.00")
