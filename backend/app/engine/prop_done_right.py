"""Prop Done Right / TDG risk policy for Topstep-style prop challenges.

This module is intentionally broker-neutral. It encodes Jared's operating
rules before any strategy or execution adapter is allowed to submit a trade:
think in drawdown, trade MYM micros only, respect the Daily Risk Budget, and
quit when the day is either protected or damaged.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor


MICRO_SYMBOLS = {"MES", "MNQ", "MYM", "MGC", "MCL", "M2K"}
MINI_SYMBOLS = {"ES", "NQ", "YM", "GC", "CL", "RTY"}


@dataclass(frozen=True)
class PropDoneRightConfig:
    """Configuration for the Prop Done Right / TDG operating system."""

    account_size: float = 50_000
    configured_drawdown: float = 2_500
    official_mll_amount: float | None = 2_000
    daily_risk_budget_pct: float = 0.10
    power_quitting_soft_multiple: float = 1.0
    power_quitting_hard_multiple: float = 2.0
    allowed_symbols: tuple[str, ...] = ("MYM",)
    blocked_symbols: tuple[str, ...] = ("MNQ", "NQ", "ES", "YM", "RTY")
    max_micro_contracts: int = 1

    @property
    def effective_drawdown(self) -> float:
        """Return the drawdown amount to size risk against.

        If an official Topstep Maximum Loss Limit is known, use the more
        conservative of the trader-configured drawdown and official MLL.
        """
        if self.official_mll_amount is None:
            return float(self.configured_drawdown)
        return float(min(self.configured_drawdown, self.official_mll_amount))

    @property
    def daily_risk_budget(self) -> float:
        """Maximum permitted net loss for one trading day."""
        return self.effective_drawdown * self.daily_risk_budget_pct

    @property
    def power_quitting_soft_profit(self) -> float:
        """Profit level where the operator should consider stopping."""
        return self.daily_risk_budget * self.power_quitting_soft_multiple

    @property
    def power_quitting_hard_profit(self) -> float:
        """Profit level where automation should stop opening new trades."""
        return self.daily_risk_budget * self.power_quitting_hard_multiple


@dataclass(frozen=True)
class TradeGateInput:
    symbol: str
    day_pnl: float
    proposed_contracts: int
    current_open_contracts: int = 0


@dataclass(frozen=True)
class TradeGateDecision:
    allowed: bool
    action: str
    reason: str


def evaluate_trade_gate(gate_input: TradeGateInput, config: PropDoneRightConfig | None = None) -> TradeGateDecision:
    """Evaluate whether a new trade is allowed under Prop Done Right rules."""
    cfg = config or PropDoneRightConfig()
    symbol = gate_input.symbol.upper()

    if symbol in MINI_SYMBOLS:
        return TradeGateDecision(False, "block_entry", f"{symbol} blocked: micros only, never minis")

    if symbol not in MICRO_SYMBOLS:
        return TradeGateDecision(False, "block_entry", f"{symbol} blocked: unknown or non-micro symbol")

    if symbol in cfg.blocked_symbols:
        return TradeGateDecision(False, "block_entry", f"{symbol} blocked by profile; start with MYM only")

    if symbol not in cfg.allowed_symbols:
        return TradeGateDecision(False, "block_entry", f"{symbol} blocked: MYM only during initial discipline phase")

    if gate_input.day_pnl <= -cfg.daily_risk_budget:
        return TradeGateDecision(
            False,
            "daily_lockout",
            f"Daily Risk Budget hit (${cfg.daily_risk_budget:.2f}); stop trading immediately",
        )

    if gate_input.day_pnl >= cfg.power_quitting_hard_profit:
        return TradeGateDecision(
            False,
            "profit_lockout",
            f"Power of Quitting hard lock hit at ${gate_input.day_pnl:.2f}; protect the day",
        )

    total_contracts = gate_input.current_open_contracts + gate_input.proposed_contracts
    if gate_input.proposed_contracts < 1:
        return TradeGateDecision(False, "block_entry", "proposed contract quantity must be at least 1 micro")

    if total_contracts > cfg.max_micro_contracts:
        return TradeGateDecision(
            False,
            "block_entry",
            f"contract cap exceeded: {total_contracts} > {cfg.max_micro_contracts} micro contract(s)",
        )

    if gate_input.day_pnl >= cfg.power_quitting_soft_profit:
        return TradeGateDecision(
            True,
            "warn_power_quitting",
            f"Power of Quitting soft level reached at ${gate_input.day_pnl:.2f}; consider stopping",
        )

    return TradeGateDecision(True, "allow", "trade passes Prop Done Right gate")


def mym_micro_contracts_for_risk(risk_budget: float, stop_ticks: int, round_turn_fees: float = 0.0) -> int:
    """Calculate integer MYM micro contracts for a stop distance and risk budget.

    MYM tick value is $0.50 per micro contract. Size is floored; if one micro
    contract exceeds the allowed risk, return 0 so the strategy skips the trade.
    """
    if risk_budget <= 0 or stop_ticks <= 0:
        return 0

    dollars_per_contract = stop_ticks * 0.50 + round_turn_fees
    if dollars_per_contract <= 0:
        return 0

    return max(0, floor(risk_budget / dollars_per_contract))
