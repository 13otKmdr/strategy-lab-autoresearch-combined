"""Topstep Trading Combine rule model.

This module models official challenge mechanics separately from the stricter
Prop Done Right operating profile. It is pure Python and intentionally has no
ProjectX dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopstepDay:
    net_profit: float


@dataclass(frozen=True)
class TopstepCombineRules:
    account_size: float
    profit_target: float
    maximum_loss_limit: float
    daily_loss_limit: float | None = 1_000
    min_trading_days: int = 1

    @classmethod
    def topstep_50k(cls) -> "TopstepCombineRules":
        return cls(
            account_size=50_000,
            profit_target=3_000,
            maximum_loss_limit=2_000,
            daily_loss_limit=1_000,
            min_trading_days=1,
        )

    @property
    def initial_mll_floor(self) -> float:
        return self.account_size - self.maximum_loss_limit

    def mll_floor_for_highest_eod_balance(self, highest_eod_balance: float) -> float:
        trailing_floor = highest_eod_balance - self.maximum_loss_limit
        return min(self.account_size, trailing_floor)

    def consistency_passes(self, total_profit: float, best_day_profit: float) -> bool:
        if total_profit < self.profit_target:
            return False
        if total_profit <= 0:
            return False
        return (best_day_profit / total_profit) < 0.50

    def challenge_passes(self, days: list[TopstepDay]) -> bool:
        if len(days) < self.min_trading_days:
            return False
        profits = [d.net_profit for d in days]
        total_profit = sum(profits)
        best_day_profit = max(profits, default=0.0)
        return total_profit >= self.profit_target and self.consistency_passes(total_profit, best_day_profit)


class TopstepPathState:
    """Mutable MLL state for a simulated Trading Combine path."""

    def __init__(self, rules: TopstepCombineRules):
        self.rules = rules
        self.highest_eod_balance = rules.account_size
        self.mll_floor = rules.initial_mll_floor

    def apply_end_of_day_balance(self, balance: float) -> float:
        if balance > self.highest_eod_balance:
            self.highest_eod_balance = balance
        self.mll_floor = max(
            self.mll_floor,
            self.rules.mll_floor_for_highest_eod_balance(self.highest_eod_balance),
        )
        return self.mll_floor

    def current_equity(self, realized_pnl: float, unrealized_pnl: float = 0.0, fees: float = 0.0) -> float:
        return self.rules.account_size + realized_pnl + unrealized_pnl - fees

    def is_mll_breached(self, realized_pnl: float, unrealized_pnl: float = 0.0, fees: float = 0.0) -> bool:
        return self.current_equity(realized_pnl, unrealized_pnl, fees) <= self.mll_floor
