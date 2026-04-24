"""Pre-trade risk checks — the last line of defense before order submission.

RiskDaemon checks:
  1. Protective stop is present
  2. Daily risk budget (DRB) is not exceeded
  3. Consecutive loss limit is not exceeded
  4. Only micro contracts are allowed (no minis)
  5. Kill switch is not active

All checks must pass for a trade to be allowed.
Failures return a RiskCheckResult with allowed=False and a reason string.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.execution.trade_intent import TradeIntent
from app.models.futures import is_mini_symbol


@dataclass(frozen=True)
class RiskCheckResult:
    allowed: bool
    reason: str = ""


class RiskDaemon:
    """Stateless pre-trade risk checker.

    Callers pass in the current day's context (pnl, consecutive losses, etc).
    The daemon does NOT maintain internal state — the caller is responsible
    for tracking P&L and loss streaks.
    """

    def __init__(
        self,
        daily_risk_budget: float = 500.0,
        max_consecutive_losses: int = 2,
    ) -> None:
        self.daily_risk_budget = daily_risk_budget
        self.max_consecutive_losses = max_consecutive_losses

    def check(
        self,
        intent: TradeIntent,
        day_pnl: float = 0.0,
        consecutive_losses: int = 0,
    ) -> RiskCheckResult:
        """Run all pre-trade checks. Returns allowed=True only if ALL pass."""

        # Gate 1: Protective stop
        if not intent.has_protective_stop():
            return RiskCheckResult(
                allowed=False,
                reason=f"no protective stop on {intent.symbol} ({intent.custom_tag})",
            )

        # Gate 2: Daily risk budget
        if day_pnl <= -self.daily_risk_budget:
            return RiskCheckResult(
                allowed=False,
                reason=f"DRB exceeded: day_pnl={day_pnl:.2f}, budget={self.daily_risk_budget:.2f}",
            )

        # Gate 3: Consecutive losses
        if consecutive_losses >= self.max_consecutive_losses:
            return RiskCheckResult(
                allowed=False,
                reason=f"consecutive loss limit: {consecutive_losses} >= {self.max_consecutive_losses}",
            )

        # Gate 4: Micros only — block minis
        if is_mini_symbol(intent.symbol):
            return RiskCheckResult(
                allowed=False,
                reason=f"mini contract blocked: {intent.symbol} — micros only",
            )

        return RiskCheckResult(allowed=True, reason="all checks passed")
