"""Drawdown-relative futures risk sizing for prop-challenge backtests.

Risk levels are interpreted as Daily Risk Budget (DRB) multiples by default:
0.25 means risk 25% of DRB, not 0.25% of nominal account equity.  Values
larger than 10 are treated as explicit dollar risk for compatibility with
callers that want to pass a fixed dollar budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from app.config import PROP_ALLOWED_SYMBOLS, PROP_BLOCKED_SYMBOLS, PROP_PROFILE
from app.engine.prop_done_right import PropDoneRightConfig
from app.engine.prop_profile import BROAD_RESEARCH_PROFILES
from app.models.futures import get_contract_spec
from app.models.strategy import StrategyDefinition


DRB_MULTIPLE_THRESHOLD = 10.0


@dataclass(frozen=True)
class PropRiskSizingInput:
    symbol: str
    entry_price: float
    stop_price: float
    risk_level: float
    prop_config: PropDoneRightConfig | None = None
    round_turn_fees_per_contract: float = 0.0
    enforce_prop_profile: bool | None = None


@dataclass(frozen=True)
class PropRiskSizingResult:
    contracts: int
    symbol: str
    per_trade_risk_dollars: float
    stop_ticks: int
    dollars_at_risk_per_contract: float
    skip_reason: str = ""


def default_prop_config() -> PropDoneRightConfig:
    """Build a Prop Done Right config from process config defaults."""
    return PropDoneRightConfig(
        allowed_symbols=tuple(PROP_ALLOWED_SYMBOLS),
        blocked_symbols=tuple(PROP_BLOCKED_SYMBOLS),
    )


def is_prop_profile(profile: str | None = None) -> bool:
    return (profile or PROP_PROFILE).strip().lower() not in BROAD_RESEARCH_PROFILES


def infer_symbol_from_strategy(strategy: StrategyDefinition | None, default: str = "MYM") -> str:
    if strategy is None:
        return default
    if strategy.risk.get("symbol"):
        return str(strategy.risk["symbol"]).upper()
    if strategy.risk.get("instrument"):
        return str(strategy.risk["instrument"]).upper()
    if strategy.intended_asset_classes:
        return str(strategy.intended_asset_classes[0]).upper()
    return default


def per_trade_risk_dollars(risk_level: float, config: PropDoneRightConfig | None = None) -> float:
    """Convert a risk level to dollars.

    0 < risk_level <= 10: DRB multiple, e.g. 0.25 * $200 DRB = $50.
    risk_level > 10: explicit dollar budget.
    """
    risk = float(risk_level)
    if risk <= 0:
        return 0.0
    if risk > DRB_MULTIPLE_THRESHOLD:
        return risk
    cfg = config or default_prop_config()
    return cfg.daily_risk_budget * risk


def stop_ticks_for_price_distance(symbol: str, entry_price: float, stop_price: float) -> int:
    try:
        spec = get_contract_spec(symbol)
    except ValueError:
        return 0
    distance = abs(float(entry_price) - float(stop_price))
    if distance <= 0 or spec.tick_size <= 0:
        return 0
    return int(ceil(distance / spec.tick_size))


def size_integer_micro_contracts(sizing_input: PropRiskSizingInput) -> PropRiskSizingResult:
    """Return integer futures micro contracts for DRB-dollar risk.

    If the resulting quantity is zero, callers should skip the trade.  Under the
    default prop profile this also fails closed for symbols outside the configured
    allowed list or for any non-micro contract.
    """
    symbol = sizing_input.symbol.upper()
    cfg = sizing_input.prop_config or default_prop_config()
    enforce_prop = is_prop_profile() if sizing_input.enforce_prop_profile is None else sizing_input.enforce_prop_profile
    risk_dollars = per_trade_risk_dollars(sizing_input.risk_level, cfg)

    try:
        spec = get_contract_spec(symbol)
    except ValueError:
        return PropRiskSizingResult(0, symbol, risk_dollars, 0, 0.0, f"unknown futures symbol: {symbol}")

    if enforce_prop:
        if spec.contract_type != "micro":
            return PropRiskSizingResult(0, symbol, risk_dollars, 0, 0.0, f"{symbol} blocked: micros only")
        if symbol in cfg.blocked_symbols:
            return PropRiskSizingResult(0, symbol, risk_dollars, 0, 0.0, f"{symbol} blocked by prop profile")
        if symbol not in cfg.allowed_symbols:
            return PropRiskSizingResult(0, symbol, risk_dollars, 0, 0.0, f"{symbol} not allowed by prop profile")

    stop_ticks = stop_ticks_for_price_distance(symbol, sizing_input.entry_price, sizing_input.stop_price)
    if risk_dollars <= 0:
        return PropRiskSizingResult(0, symbol, risk_dollars, stop_ticks, 0.0, "risk budget must be positive")
    if stop_ticks <= 0:
        return PropRiskSizingResult(0, symbol, risk_dollars, stop_ticks, 0.0, "stop distance must be positive")

    dollars_per_contract = stop_ticks * spec.tick_value + max(0.0, float(sizing_input.round_turn_fees_per_contract))
    if dollars_per_contract <= 0:
        return PropRiskSizingResult(0, symbol, risk_dollars, stop_ticks, dollars_per_contract, "risk per contract must be positive")

    contracts = int(max(0, floor(risk_dollars / dollars_per_contract)))
    if enforce_prop:
        contracts = min(contracts, int(cfg.max_micro_contracts))

    if contracts < 1:
        return PropRiskSizingResult(
            0,
            symbol,
            risk_dollars,
            stop_ticks,
            dollars_per_contract,
            f"one {symbol} micro risks ${dollars_per_contract:.2f}, above ${risk_dollars:.2f} budget",
        )

    return PropRiskSizingResult(contracts, symbol, risk_dollars, stop_ticks, dollars_per_contract)


def futures_position_pnl(symbol: str, entry_price: float, exit_price: float, contracts: int, direction: str) -> float:
    """Return dollar P&L for a futures position using tick size and tick value."""
    if contracts <= 0:
        return 0.0
    spec = get_contract_spec(symbol)
    tick_delta = (float(exit_price) - float(entry_price)) / spec.tick_size
    if direction == "short":
        tick_delta = -tick_delta
    return float(tick_delta * spec.tick_value * contracts)
