"""Broker adapter abstraction + concrete implementations.

BrokerAdapter is the abstract interface for all order submission.
Concrete adapters:
  - PaperBroker: simulates fills locally (no network)
  - ProjectXReadonlyAdapter: queries TopstepX/ProjectX API but NEVER places orders

The LIVE ProjectX adapter (for actual order placement) is NOT implemented yet.
Per the safety skill: "Do not implement live ProjectX order submission in the first slice."
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.execution.trade_intent import TradeIntent


@dataclass(frozen=True)
class FillResult:
    """Result of a broker submit call."""
    filled: bool
    fill_price: float
    simulated: bool
    order_id: str = ""
    broker_response: dict | None = None


class BrokerAdapter(ABC):
    """Abstract broker adapter — all submission goes through this interface."""

    @abstractmethod
    def submit(self, intent: TradeIntent) -> FillResult:
        ...

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        ...


class PaperBroker(BrokerAdapter):
    """Simulates fills at a dummy price. No network calls."""

    def __init__(self, fill_price: float = 42_000.0) -> None:
        self._fill_price = fill_price
        self._order_counter = 0

    @property
    def is_simulated(self) -> bool:
        return True

    def submit(self, intent: TradeIntent) -> FillResult:
        self._order_counter += 1
        return FillResult(
            filled=True,
            fill_price=self._fill_price,
            simulated=True,
            order_id=f"PAPER-{self._order_counter:06d}",
        )


class ProjectXReadonlyAdapter(BrokerAdapter):
    """Read-only TopstepX/ProjectX adapter.

    Can query account, positions, and orders but MUST NEVER submit.
    Use this for monitoring and reconciliation only.
    """

    @property
    def is_simulated(self) -> bool:
        return True  # never actually trades

    def submit(self, intent: TradeIntent) -> FillResult:
        raise RuntimeError(
            "read-only adapter: order submission is forbidden — "
            "use a live adapter with all safety gates"
        )

    def get_positions(self, account_id: str) -> list[dict]:
        """Query open positions via ProjectX API.

        TODO: implement with real HTTP calls to /api/Position/openPositions
        """
        return []

    def get_account(self, account_id: str) -> dict | None:
        """Query account info via ProjectX API.

        TODO: implement with real HTTP calls to /api/Account/accountSearch
        """
        return None
