"""Broker adapter abstraction + concrete implementations.

BrokerAdapter is the abstract interface for all order submission.
Concrete adapters:
  - PaperBroker: simulates fills locally (no network)
  - ProjectXReadonlyAdapter: queries TopstepX/ProjectX API but NEVER places orders
  - ProjectXLiveAdapter: places real orders via ProjectX (requires ALL safety gates)

The LIVE adapter is the only one that can place real orders, and it
requires the full safety pipeline (execution_mode gates, risk_daemon,
kill_switch, audit_log) to be satisfied before submission.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import logging

from app.execution.trade_intent import TradeIntent
from app.execution.execution_mode import ExecutionMode, require_live_gates

logger = logging.getLogger(__name__)


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

    def __init__(self, client=None):
        """Optionally inject a ProjectXClient for live queries."""
        self._client = client

    @property
    def is_simulated(self) -> bool:
        return True  # never actually trades

    def submit(self, intent: TradeIntent) -> FillResult:
        raise RuntimeError(
            "read-only adapter: order submission is forbidden — "
            "use a live adapter with all safety gates"
        )

    async def get_positions(self, account_id: int) -> list[dict]:
        """Query open positions via ProjectX API."""
        if self._client is None:
            return []
        positions = await self._client.search_open_positions(account_id)
        return [
            {
                "id": p.id,
                "contract_id": p.contract_id,
                "type": p.type,
                "size": p.size,
                "average_price": p.average_price,
            }
            for p in positions
        ]

    async def get_account(self, account_id: int) -> dict | None:
        """Query account info via ProjectX API."""
        if self._client is None:
            return None
        acct = await self._client.get_account(account_id)
        if acct is None:
            return None
        return {
            "id": acct.id,
            "name": acct.name,
            "balance": acct.balance,
            "can_trade": acct.can_trade,
        }


class ProjectXLiveAdapter(BrokerAdapter):
    """LIVE TopstepX/ProjectX adapter that places real orders.

    ⚠️  This adapter is the ONLY code path that can submit real orders.
    It enforces ALL safety gates before every single submission.

    Required gates (all must pass):
      1. Execution mode is LIVE
      2. Live feature flag is enabled
      3. Account is on the allowlist
      4. Arming token is present
      5. Kill switch is inactive
      6. Strategy is approved for live trading
      7. Protective bracket is present on the TradeIntent
    """

    def __init__(
        self,
        client,
        account_id: int,
        allowlisted_account_ids: set[str] | None = None,
        live_feature_flag: bool = False,
        arming_token: str | None = None,
    ):
        self._client = client
        self._account_id = account_id
        self._allowlisted = allowlisted_account_ids or set()
        self._live_feature_flag = live_feature_flag
        self._arming_token = arming_token

    @property
    def is_simulated(self) -> bool:
        return False  # THIS IS REAL

    @property
    def client(self):
        return self._client

    async def submit(
        self,
        intent: TradeIntent,
        strategy_approved: bool = False,
        kill_switch_active: bool = False,
    ) -> FillResult:
        """Submit a live order after passing ALL safety gates.

        Every gate must pass. If any gate fails, the order is REJECTED.
        This method also logs the gate check result to the audit trail.
        """
        from app.execution.projectx_client import OrderSide, OrderType
        from app.models.futures import get_contract_spec

        # ── Gate Check ────────────────────────────────────────────────
        try:
            require_live_gates(
                mode=ExecutionMode.LIVE,
                account_id=str(self._account_id),
                strategy_approved=strategy_approved,
                kill_switch_active=kill_switch_active,
                has_protective_bracket=intent.has_protective_stop(),
                arming_token=self._arming_token,
                live_feature_flag=self._live_feature_flag,
                allowlisted_account_ids=self._allowlisted,
            )
        except RuntimeError as e:
            logger.warning("LIVE gate blocked order %s: %s", intent.custom_tag, e)
            return FillResult(
                filled=False,
                fill_price=0.0,
                simulated=False,
                order_id="",
                broker_response={"gate_rejected": str(e)},
            )

        # ── Map direction to ProjectX side ────────────────────────────
        side = OrderSide.BUY if intent.direction == "long" else OrderSide.SELL

        # ── Map entry_type to ProjectX order type ─────────────────────
        order_type = (
            OrderType.MARKET if intent.entry_type == "market"
            else OrderType.LIMIT
        )

        limit_price = intent.limit_price if intent.entry_type == "limit" else None

        # ── Submit via ProjectX API ───────────────────────────────────
        result = await self._client.place_order(
            account_id=self._account_id,
            contract_id=intent.contract_id,
            side=side,
            size=intent.quantity,
            order_type=order_type,
            limit_price=limit_price,
            custom_tag=intent.custom_tag,
            stop_loss_ticks=intent.stop_loss_ticks if intent.stop_loss_ticks > 0 else None,
            take_profit_ticks=intent.take_profit_ticks if intent.take_profit_ticks > 0 else None,
        )

        return FillResult(
            filled=result.success,
            fill_price=0.0,  # fill price comes from position update
            simulated=False,
            order_id=str(result.order_id) if result.order_id else "",
            broker_response={
                "order_id": result.order_id,
                "error_code": result.error_code,
                "error_message": result.error_message,
            },
        )


# ── Broker Factory ───────────────────────────────────────────────────────────

def create_broker(
    mode: ExecutionMode,
    account_id: int = 0,
    client=None,
    allowlisted_account_ids: set[str] | None = None,
    live_feature_flag: bool = False,
    arming_token: str | None = None,
) -> BrokerAdapter:
    """Factory: create the right broker for the execution mode.

    READ_ONLY / DRY_RUN → ProjectXReadonlyAdapter (or no client)
    PAPER               → PaperBroker
    LIVE                → ProjectXLiveAdapter (requires all safety params)
    """
    if mode in (ExecutionMode.READ_ONLY, ExecutionMode.DRY_RUN):
        return ProjectXReadonlyAdapter(client=client)
    elif mode == ExecutionMode.PAPER:
        return PaperBroker()
    elif mode == ExecutionMode.LIVE:
        return ProjectXLiveAdapter(
            client=client,
            account_id=account_id,
            allowlisted_account_ids=allowlisted_account_ids,
            live_feature_flag=live_feature_flag,
            arming_token=arming_token,
        )
    else:
        raise ValueError(f"Unknown execution mode: {mode}")
