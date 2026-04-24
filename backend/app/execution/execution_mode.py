"""Execution mode safety ladder.

Modes (in order of increasing trust):
  READ_ONLY  → can only query, never place orders
  DRY_RUN    → simulates full pipeline but never calls broker API
  PAPER      → places simulated orders via PaperBroker
  LIVE       → places real orders via ProjectX adapter (requires all gates)

Default is READ_ONLY. LIVE requires every safety gate to pass.
"""
from __future__ import annotations

from enum import Enum


class ExecutionMode(Enum):
    READ_ONLY = "read_only"
    DRY_RUN = "dry_run"
    PAPER = "paper"
    LIVE = "live"

    @property
    def can_place_orders(self) -> bool:
        return self in (ExecutionMode.PAPER, ExecutionMode.LIVE)

    @property
    def is_simulated(self) -> bool:
        return self in (ExecutionMode.READ_ONLY, ExecutionMode.DRY_RUN, ExecutionMode.PAPER)

    @classmethod
    def from_string(cls, value: str | None) -> "ExecutionMode":
        if value is None:
            return cls.READ_ONLY
        return cls(value.lower().replace("-", "_"))


def require_live_gates(
    mode: ExecutionMode,
    account_id: str,
    strategy_approved: bool,
    kill_switch_active: bool,
    has_protective_bracket: bool,
    arming_token: str | None = None,
    live_feature_flag: bool = False,
    allowlisted_account_ids: set[str] | None = None,
) -> None:
    """Validate ALL safety gates before LIVE trading.

    Raises RuntimeError with a descriptive message on any gate failure.
    This function is called at the single point where live order submission happens.
    """
    if mode != ExecutionMode.LIVE:
        return  # gates only apply to LIVE mode

    if not live_feature_flag:
        raise RuntimeError("live gate: live feature flag is not enabled")

    if not allowlisted_account_ids or account_id not in allowlisted_account_ids:
        raise RuntimeError(
            f"live gate: account {account_id} is not on the allowlist"
        )

    if not arming_token:
        raise RuntimeError("live gate: arming token is missing")

    if kill_switch_active:
        raise RuntimeError("live gate: kill switch is active — trading halted")

    if not strategy_approved:
        raise RuntimeError("live gate: strategy is not approved for live trading")

    if not has_protective_bracket:
        raise RuntimeError("live gate: protective bracket/stop is missing")
