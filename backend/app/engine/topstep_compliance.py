"""Topstep Trading Combine compliance validator for generated strategies.

This module enforces Topstep-specific rules that the strategy generator does
not natively enforce. It runs BEFORE backtesting and execution to reject
strategies that would violate prop-firm rules:

  1. Min hold time: at least 1 bar (15 min) — no scalping / HFT
  2. Max hold time: capped at ~1 RTH session — no overnight holding
  3. Session filter: only RTH (US Regular) allowed — flat by close
  4. Direction lock: no "both" — prevents hedging
  5. Fundamental filters: advisory warnings for missing news avoidance
  6. Market type: must be futures

This is the strategy-level gate. Execution-level gates (DRB, MLL, contract
limits, anti-hedging on same account) are in prop_done_right.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.strategy import StrategyDefinition


# ── Configuration ─────────────────────────────────────────────────────────────

# RTH session for futures: 9:30 AM – 4:00 PM ET
# At 15-min bars, one RTH session = 26 bars (6.5 hours)
_BARS_PER_RTH_SESSION = 26


@dataclass(frozen=True)
class TopstepComplianceConfig:
    """Configuration for Topstep strategy compliance checks."""

    min_hold_bars: int = 1                # Minimum hold: 1 bar = 15 min
    max_hold_bars: int = _BARS_PER_RTH_SESSION  # Max hold: 1 RTH session = 26 bars
    allowed_sessions: frozenset[str] = frozenset({"us_regular"})
    require_fundamental_filters: bool = False  # Advisory, not blocking
    required_news_events: tuple[str, ...] = ("fomc", "nfp", "cpi")
    require_single_direction: bool = True     # Block "both" direction
    allowed_market_types: frozenset[str] = frozenset({"futures"})


DEFAULT_CONFIG = TopstepComplianceConfig()


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ComplianceResult:
    """Result of validating a single strategy against Topstep rules."""
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    strategy_id: str = ""
    strategy_name: str = ""
    strategy: StrategyDefinition | None = None


@dataclass
class BatchComplianceResult:
    """Result of validating a batch of strategies."""
    passed: list[StrategyDefinition]
    failed: list[ComplianceResult]
    total: int = 0

    @property
    def passed_count(self) -> int:
        return len(self.passed)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


# ── Core validator ────────────────────────────────────────────────────────────

def validate_strategy(
    strategy: StrategyDefinition,
    config: TopstepComplianceConfig | None = None,
) -> ComplianceResult:
    """Validate a single strategy definition against Topstep compliance rules.

    Returns a ComplianceResult with passed=True/False, violation messages,
    and advisory warnings.
    """
    cfg = config or DEFAULT_CONFIG
    violations: list[str] = []
    warnings: list[str] = []

    # ── Check 1: Market type ──────────────────────────────────────────────
    if strategy.market_type not in cfg.allowed_market_types:
        violations.append(
            f"Market type '{strategy.market_type}' not allowed; "
            f"Topstep requires: {sorted(cfg.allowed_market_types)}"
        )

    # ── Check 2: Min hold time ────────────────────────────────────────────
    exit_rules = strategy.exit_rules or {}
    exit_dict = strategy.exit or {}
    # Prefer exit_rules, then fall back to exit dict
    if "time_exit_bars" in exit_rules:
        time_exit = exit_rules["time_exit_bars"]
    else:
        time_exit = exit_dict.get("time_exit_bars")

    if time_exit is None:
        violations.append(
            "No time_exit_bars set — strategy has no minimum hold time. "
            "Topstep prohibits HFT/scalping. Set time_exit_bars >= "
            f"{cfg.min_hold_bars} bars."
        )
    elif time_exit < cfg.min_hold_bars:
        violations.append(
            f"time_exit_bars={time_exit} is below minimum of {cfg.min_hold_bars}. "
            "Strategy could exit too quickly (HFT/scalping risk)."
        )

    # ── Check 3: Max hold time ────────────────────────────────────────────
    if time_exit is not None and time_exit > cfg.max_hold_bars:
        violations.append(
            f"time_exit_bars={time_exit} exceeds maximum of {cfg.max_hold_bars} bars "
            f"({cfg.max_hold_bars * 15} min). Strategy may hold overnight, "
            "violating Topstep flat-by-close requirement."
        )

    # ── Check 4: Session filter ───────────────────────────────────────────
    session_filters = strategy.session_filters or {}
    allowed_sessions = session_filters.get("allowed_sessions", [])

    if not allowed_sessions:
        violations.append(
            "No session filter set — strategy could trade any session including "
            "overnight. Topstep requires flat by close."
        )
    else:
        disallowed = set(allowed_sessions) - cfg.allowed_sessions
        if disallowed:
            violations.append(
                f"Disallowed session(s): {sorted(disallowed)}. "
                f"Only {sorted(cfg.allowed_sessions)} permitted under Topstep rules. "
                "Overnight and extended-hour trading is prohibited."
            )

    # ── Check 5: Direction / anti-hedging ─────────────────────────────────
    if cfg.require_single_direction:
        entry_rules = strategy.entry_rules or {}
        direction = entry_rules.get("direction", "").lower()
        # Also check the strategy-level entry dict
        entry_dict = strategy.entry or {}
        if not direction:
            direction = entry_dict.get("direction", "").lower()

        if direction == "both":
            violations.append(
                "Direction 'both' allows simultaneous long and short entries "
                "on the same instrument. Topstep prohibits hedging. "
                "Use 'long' or 'short' only."
            )

    # ── Check 6: Fundamental filters (advisory) ───────────────────────────
    fund_filters = strategy.fundamental_filters_if_any or {}
    if not fund_filters:
        warnings.append(
            "No fundamental filters set. High-impact news events (FOMC, NFP, CPI) "
            "can cause extreme slippage. Consider adding avoid_fomc/avoid_nfp/avoid_cpi."
        )
    else:
        missing_events = [
            event for event in cfg.required_news_events
            if not fund_filters.get(f"avoid_{event}", False)
        ]
        if missing_events:
            missing_upper = [e.upper() for e in missing_events]
            warnings.append(
                f"Fundamental filters missing for: {', '.join(missing_upper)}. "
                "These events cause volatile spikes that can trigger stops or MLL breaches."
            )

    passed = len(violations) == 0
    return ComplianceResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
        strategy_id=strategy.strategy_id,
        strategy_name=strategy.strategy_name,
        strategy=strategy,
    )


def validate_strategy_batch(
    strategies: list[StrategyDefinition],
    config: TopstepComplianceConfig | None = None,
) -> BatchComplianceResult:
    """Validate a batch of strategies, separating compliant from non-compliant.

    Returns a BatchComplianceResult with:
      - passed: list of StrategyDefinition objects that passed all checks
      - failed: list of ComplianceResult objects for strategies that failed
    """
    cfg = config or DEFAULT_CONFIG
    passed_strats: list[StrategyDefinition] = []
    failed_results: list[ComplianceResult] = []

    for strat in strategies:
        result = validate_strategy(strat, config=cfg)
        if result.passed:
            passed_strats.append(strat)
        else:
            failed_results.append(result)

    return BatchComplianceResult(
        passed=passed_strats,
        failed=failed_results,
        total=len(strategies),
    )
