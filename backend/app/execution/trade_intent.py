"""Broker-neutral trade intent model for the execution layer.

TradeIntent is the ONLY object that crosses the research → execution boundary.
It enforces integer quantities and valid directions at construction time.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeIntent:
    """Immutable, broker-neutral order descriptor.

    Every live trade MUST have a protective stop (stop_loss_ticks > 0).
    The risk daemon enforces this at submission time.
    """

    strategy_id: str
    symbol: str
    contract_id: str  # e.g. "CON.F.US.MYM.M26"
    direction: str     # "long" | "short"
    quantity: int
    entry_type: str    # "market" | "limit"
    stop_loss_ticks: int
    take_profit_ticks: int
    custom_tag: str    # idempotency key

    limit_price: float | None = None

    def __post_init__(self):
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got '{self.direction}'")
        if not isinstance(self.quantity, int) or self.quantity != float(self.quantity):
            raise ValueError(f"quantity must be an integer, got {self.quantity!r}")
        if self.quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {self.quantity}")

    def has_protective_stop(self) -> bool:
        """True if a real stop-loss is defined (> 0 ticks)."""
        return self.stop_loss_ticks > 0
