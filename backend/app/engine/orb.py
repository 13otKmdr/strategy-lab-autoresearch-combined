"""
Opening Range Breakout (ORB) strategy engine.

Self-contained bar-by-bar simulator that identifies the opening range,
generates entry signals on breakout, and manages exits via stop loss,
take profit, and time-based rules.  Returns the same BacktestResult /
Trade format used by the main backtester so results are interchangeable.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from itertools import product

import numpy as np

from app.config import COMMISSION_FLAT, COMMISSION_PCT, SLIPPAGE_PCT, WARMUP_BARS
from app.engine.prop_risk_sizing import PropRiskSizingInput, futures_position_pnl, size_integer_micro_contracts
from app.models.backtest import BacktestResult, Trade
from app.models.market import Candle
from app.models.strategy import StrategyDefinition


# ---------------------------------------------------------------------------
# Opening range detection
# ---------------------------------------------------------------------------

def detect_opening_range(
    candles: list[Candle],
    session_start_hour: int = 9,
    session_start_minute: int = 30,
    range_bars: int = 2,
) -> list[dict]:
    """Scan *candles* and return one record per detected opening range.

    Each record contains:
        range_high   – highest high within the opening-range bars
        range_low    – lowest low within the opening-range bars
        start_idx    – index of the first bar of the range
        end_idx      – index of the last bar of the range (inclusive)
        range_size   – range_high - range_low

    Multiple ranges are returned when the data spans multiple sessions.
    """
    ranges: list[dict] = []
    n = len(candles)
    i = 0

    while i < n:
        dt = datetime.fromtimestamp(candles[i].ts / 1000, tz=timezone.utc)
        if dt.hour == session_start_hour and dt.minute == session_start_minute:
            end = min(i + range_bars, n)
            if end - i < range_bars:
                i += 1
                continue
            rng_high = max(c.high for c in candles[i:end])
            rng_low = min(c.low for c in candles[i:end])
            ranges.append({
                "range_high": rng_high,
                "range_low": rng_low,
                "start_idx": i,
                "end_idx": end - 1,
                "range_size": rng_high - rng_low,
            })
            i = end  # skip past the range bars
        else:
            i += 1

    return ranges


# ---------------------------------------------------------------------------
# ATR helper (simple True Range average, no dependency on indicators module)
# ---------------------------------------------------------------------------

def _atr(candles: list[Candle], period: int = 14) -> np.ndarray:
    n = len(candles)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i - 1].close),
            abs(candles[i].low - candles[i - 1].close),
        )
    atr_arr = np.full(n, np.nan)
    if n > period:
        atr_arr[period] = np.mean(tr[1 : period + 1])
        for i in range(period + 1, n):
            atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / period
    return atr_arr


# ---------------------------------------------------------------------------
# Commission helper (mirrors backtester._commission)
# ---------------------------------------------------------------------------

def _commission(contracts: float) -> float:
    return COMMISSION_FLAT * abs(contracts)


# ---------------------------------------------------------------------------
# ORB backtester
# ---------------------------------------------------------------------------

def run_orb_backtest(
    strategy_config: dict,
    candles: list[Candle],
    risk_pct: float = 0.25,
    initial_capital: float = 50_000.0,
) -> BacktestResult:
    """Run a bar-by-bar ORB backtest.

    *strategy_config* keys:
        strategy_id         – unique id
        range_bars          – int, number of bars forming the opening range
        direction           – "long" | "short" | "both"
        stop_atr_buffer     – float, ATR multiple added to opposite range side
        tp_r_multiple       – float, R-multiple for take-profit target
        time_exit_bars      – int, max bars in trade before forced exit
        session_start_hour  – int (default 9)
        session_start_minute – int (default 30)
    """
    strategy_id = strategy_config["strategy_id"]
    range_bars = strategy_config.get("range_bars", 2)
    direction = strategy_config.get("direction", "long")
    stop_atr_buffer = strategy_config.get("stop_atr_buffer", 0.25)
    tp_r_multiple = strategy_config.get("tp_r_multiple", 2.0)
    time_exit_bars = strategy_config.get("time_exit_bars", 16)
    session_start_hour = strategy_config.get("session_start_hour", 9)
    session_start_minute = strategy_config.get("session_start_minute", 30)
    symbol = strategy_config.get("symbol") or strategy_config.get("instrument") or "MYM"

    n = len(candles)
    if n < WARMUP_BARS + range_bars + 2:
        return _empty_result(strategy_id, risk_pct, initial_capital, n)

    # Pre-compute ATR and opening ranges
    atr_arr = _atr(candles, period=14)
    ranges = detect_opening_range(candles, session_start_hour, session_start_minute, range_bars)

    equity = initial_capital
    equity_curve = [initial_capital] * n
    completed_trades: list[Trade] = []
    open_position: dict | None = None

    # Build a map: bar_index -> opening range that just completed
    # A range becomes "active" on the bar after its last bar
    range_active: dict[int, dict] = {}
    for rng in ranges:
        activate_bar = rng["end_idx"] + 1
        if activate_bar < n:
            range_active[activate_bar] = rng

    current_range: dict | None = None

    for i in range(WARMUP_BARS, n):
        # Activate a new opening range if one starts at this bar
        if i in range_active:
            current_range = range_active[i]

        bar = candles[i]

        # --- Check exit for open position ---
        if open_position is not None:
            trade = _check_orb_exit(open_position, candles, i, time_exit_bars, equity)
            if trade is not None:
                equity += trade.pnl
                completed_trades.append(trade)
                open_position = None

        # --- Check entry (only if no open position and we have a valid range) ---
        if open_position is None and current_range is not None and i > current_range["end_idx"]:
            atr_val = atr_arr[i]
            if math.isnan(atr_val) or atr_val <= 0:
                atr_val = bar.close * 0.02  # fallback

            rng_high = current_range["range_high"]
            rng_low = current_range["range_low"]
            rng_size = current_range["range_size"]

            if rng_size <= 0:
                equity_curve[i] = equity
                continue

            # Long breakout: close breaks above range high
            long_signal = direction in ("long", "both") and bar.close > rng_high
            # Short breakout: close breaks below range low
            short_signal = direction in ("short", "both") and bar.close < rng_low

            if long_signal:
                entry_price = bar.close * (1 + SLIPPAGE_PCT)
                stop_price = rng_low - stop_atr_buffer * atr_val
                risk_dist = abs(entry_price - stop_price)
                if risk_dist <= 0:
                    equity_curve[i] = equity
                    continue
                tp_price = entry_price + risk_dist * tp_r_multiple

                sizing = size_integer_micro_contracts(PropRiskSizingInput(
                    symbol=symbol,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    risk_level=risk_pct,
                ))
                if sizing.contracts <= 0:
                    equity_curve[i] = equity
                    continue
                size = sizing.contracts
                risk_usd = sizing.contracts * sizing.dollars_at_risk_per_contract
                cost = _commission(size)

                open_position = {
                    "entry_bar": i,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "tp_price": tp_price,
                    "size": size,
                    "symbol": symbol,
                    "entry_cost": cost,
                    "risk_usd": risk_usd,
                    "direction": "long",
                    "entry_ts": candles[i].ts,
                }
                # Invalidate range so we don't re-enter on same range
                current_range = None

            elif short_signal:
                entry_price = bar.close * (1 - SLIPPAGE_PCT)
                stop_price = rng_high + stop_atr_buffer * atr_val
                risk_dist = abs(stop_price - entry_price)
                if risk_dist <= 0:
                    equity_curve[i] = equity
                    continue
                tp_price = entry_price - risk_dist * tp_r_multiple

                sizing = size_integer_micro_contracts(PropRiskSizingInput(
                    symbol=symbol,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    risk_level=risk_pct,
                ))
                if sizing.contracts <= 0:
                    equity_curve[i] = equity
                    continue
                size = sizing.contracts
                risk_usd = sizing.contracts * sizing.dollars_at_risk_per_contract
                cost = _commission(size)

                open_position = {
                    "entry_bar": i,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "tp_price": tp_price,
                    "size": size,
                    "symbol": symbol,
                    "entry_cost": cost,
                    "risk_usd": risk_usd,
                    "direction": "short",
                    "entry_ts": candles[i].ts,
                }
                current_range = None

        equity_curve[i] = equity

    # Force-close any remaining open position
    if open_position is not None:
        is_short = open_position["direction"] == "short"
        exit_price = candles[-1].close * (1 + SLIPPAGE_PCT if is_short else 1 - SLIPPAGE_PCT)
        cost = _commission(open_position["size"])
        gross_pnl = futures_position_pnl(
            open_position.get("symbol", "MYM"),
            open_position["entry_price"],
            exit_price,
            open_position["size"],
            open_position["direction"],
        )
        net_pnl = gross_pnl - open_position.get("entry_cost", 0.0) - cost
        equity += net_pnl
        equity_curve[-1] = equity
        completed_trades.append(Trade(
            entry_bar=open_position["entry_bar"],
            exit_bar=n - 1,
            entry_price=open_position["entry_price"],
            exit_price=exit_price,
            size=open_position["size"],
            direction=open_position["direction"],
            pnl=net_pnl,
            pnl_pct=net_pnl / (open_position["entry_price"] * open_position["size"])
            if open_position["entry_price"] * open_position["size"] > 0
            else 0,
            r_multiple=net_pnl / open_position["risk_usd"] if open_position["risk_usd"] > 0 else 0,
            exit_reason="end_of_data",
            entry_ts=open_position["entry_ts"],
            exit_ts=candles[-1].ts,
        ))

    return _build_result(strategy_id, risk_pct, initial_capital, completed_trades, equity_curve, candles)


# ---------------------------------------------------------------------------
# Exit logic
# ---------------------------------------------------------------------------

def _check_orb_exit(
    pos: dict,
    candles: list[Candle],
    i: int,
    time_exit_bars: int,
    equity: float,
) -> Trade | None:
    bar = candles[i]
    is_short = pos["direction"] == "short"

    exit_price = None
    exit_reason = None

    if is_short:
        if bar.high >= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 + SLIPPAGE_PCT), "stop_loss"
        elif bar.low <= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 + SLIPPAGE_PCT), "take_profit"
        elif time_exit_bars and (i - pos["entry_bar"]) >= time_exit_bars:
            exit_price, exit_reason = bar.close * (1 + SLIPPAGE_PCT), "time_exit"
    else:
        if bar.low <= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 - SLIPPAGE_PCT), "stop_loss"
        elif bar.high >= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 - SLIPPAGE_PCT), "take_profit"
        elif time_exit_bars and (i - pos["entry_bar"]) >= time_exit_bars:
            exit_price, exit_reason = bar.close * (1 - SLIPPAGE_PCT), "time_exit"

    if exit_price is None:
        return None

    cost = _commission(pos["size"])
    gross_pnl = futures_position_pnl(pos.get("symbol", "MYM"), pos["entry_price"], exit_price, pos["size"], pos["direction"])
    net_pnl = gross_pnl - pos.get("entry_cost", 0.0) - cost

    return Trade(
        entry_bar=pos["entry_bar"],
        exit_bar=i,
        entry_price=pos["entry_price"],
        exit_price=exit_price,
        size=pos["size"],
        direction=pos["direction"],
        pnl=net_pnl,
        pnl_pct=net_pnl / (pos["entry_price"] * pos["size"])
        if pos["entry_price"] * pos["size"] > 0
        else 0,
        r_multiple=net_pnl / pos["risk_usd"] if pos["risk_usd"] > 0 else 0,
        exit_reason=exit_reason,
        entry_ts=pos["entry_ts"],
        exit_ts=candles[i].ts,
    )


# ---------------------------------------------------------------------------
# Strategy generation
# ---------------------------------------------------------------------------

def generate_orb_strategies(instrument: str, n: int = 30) -> list[StrategyDefinition]:
    """Generate *n* ORB strategy variations for *instrument*.

    Varies: range_bars, direction, stop_atr_buffer, tp_r_multiple, time_exit_bars.
    Returns StrategyDefinition objects with ORB config stored in the ``exit``
    and ``entry`` dicts so the rest of the pipeline can identify them.
    """
    range_bars_opts = [2, 3, 4]
    direction_opts = ["long", "short", "both"]
    stop_buffer_opts = [0.0, 0.25, 0.5]
    tp_r_opts = [1.5, 2.0, 3.0, 4.0]
    time_exit_opts = [8, 16, 24]

    combos = list(product(range_bars_opts, direction_opts, stop_buffer_opts, tp_r_opts, time_exit_opts))

    # Deterministic selection: evenly spaced across the full grid
    step = max(1, len(combos) // n)
    selected = combos[::step][:n]
    # If we still need more (rounding), take from the remainder
    if len(selected) < n:
        remaining = [c for c in combos if c not in selected]
        selected += remaining[: n - len(selected)]

    strategies: list[StrategyDefinition] = []
    for idx, (rb, dirn, sb, tp_r, te) in enumerate(selected, start=1):
        sid = f"ORB_{instrument}_{idx:03d}"
        name = f"ORB {dirn} rb{rb} stop{sb} tp{tp_r}R te{te} ({instrument})"

        orb_config = {
            "range_bars": rb,
            "direction": dirn,
            "stop_atr_buffer": sb,
            "tp_r_multiple": tp_r,
            "time_exit_bars": te,
        }

        strategies.append(StrategyDefinition(
            strategy_id=sid,
            strategy_name=name,
            strategy_type="breakout",
            market_type="futures",
            thesis_summary=(
                f"Opening Range Breakout: enter on {dirn} breakout of first "
                f"{rb} bars, stop at opposite range + {sb}*ATR, TP at {tp_r}R, "
                f"time exit after {te} bars."
            ),
            indicators_used=[{"type": "ATR", "params": {"period": 14}}],
            candlestick_patterns_used=[],
            timeframe_stack=["15min"],
            entry_rules={
                "trigger": "ORB_BREAKOUT",
                "filter": "NONE",
                "description": f"Price breaks {'above' if dirn == 'long' else 'below' if dirn == 'short' else 'above/below'} opening range",
            },
            exit_rules={
                "stop_loss": {"type": "range_atr", "value": sb},
                "take_profit": {"type": "r_multiple", "value": tp_r},
                "time_exit_bars": te,
            },
            stop_loss_logic={"type": "range_atr", "value": sb},
            take_profit_logic={"type": "r_multiple", "value": tp_r},
            trailing_stop_or_break_even_logic={},
            session_filters={"allowed_sessions": ["us_open"], "avoid_first_minutes": 0},
            volatility_filters={},
            fundamental_filters_if_any={},
            intended_asset_classes=[instrument],
            primary_indicator={"type": "ATR", "params": {"period": 14}},
            confirmation_indicator={},
            entry={"trigger": "ORB_BREAKOUT", "filter": "NONE", "orb_config": orb_config},
            exit={
                "stop_loss": {"type": "range_atr", "value": sb},
                "take_profit": {"type": "r_multiple", "value": tp_r},
                "time_exit_bars": te,
            },
            risk={"max_open_positions": 1},
        ))

    return strategies


def orb_config_from_strategy(strategy: StrategyDefinition) -> dict:
    """Extract the ORB config dict from a StrategyDefinition for use with run_orb_backtest."""
    orb = strategy.entry.get("orb_config", {})
    return {
        "strategy_id": strategy.strategy_id,
        "symbol": strategy.intended_asset_classes[0] if strategy.intended_asset_classes else "MYM",
        "range_bars": orb.get("range_bars", 2),
        "direction": orb.get("direction", "long"),
        "stop_atr_buffer": orb.get("stop_atr_buffer", 0.25),
        "tp_r_multiple": orb.get("tp_r_multiple", 2.0),
        "time_exit_bars": orb.get("time_exit_bars", 16),
    }


# ---------------------------------------------------------------------------
# Result builder (mirrors backtester metric computation)
# ---------------------------------------------------------------------------

def _empty_result(
    strategy_id: str, risk_pct: float, initial_capital: float, n: int,
) -> BacktestResult:
    return BacktestResult(
        strategy_id=strategy_id,
        risk_pct=risk_pct,
        initial_capital=initial_capital,
        total_return_pct=0.0,
        net_profit_dollars=0.0,
        gross_profit=0.0,
        gross_loss=0.0,
        profit_factor=0.0,
        win_rate=0.0,
        avg_r_multiple=0.0,
        total_trades=0,
        max_drawdown_pct=0.0,
        max_drawdown_dollars=0.0,
        best_trade=0.0,
        worst_trade=0.0,
        long_side_performance={"total_trades": 0, "win_rate": 0, "gross_profit": 0, "gross_loss": 0, "net_pnl": 0, "avg_r_multiple": 0},
        short_side_performance={"total_trades": 0, "win_rate": 0, "gross_profit": 0, "gross_loss": 0, "net_pnl": 0, "avg_r_multiple": 0},
        monthly_returns=[],
        equity_curve=[initial_capital] * max(n, 1),
        drawdown_curve=[0.0] * max(n, 1),
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        compliance_status="compliant",
        compliance_reason="",
        trades=[],
    )


def _build_result(
    strategy_id: str,
    risk_pct: float,
    initial_capital: float,
    trades: list[Trade],
    equity_curve: list[float],
    candles: list[Candle],
) -> BacktestResult:
    final_equity = equity_curve[-1] if equity_curve else initial_capital
    net_profit = final_equity - initial_capital
    total_return_pct = net_profit / initial_capital if initial_capital > 0 else 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_r = sum(t.r_multiple for t in trades) / len(trades) if trades else 0.0

    best_trade = max((t.pnl for t in trades), default=0.0)
    worst_trade = min((t.pnl for t in trades), default=0.0)

    # Drawdown
    dd_pct, dd_dollars = _max_drawdown(equity_curve)

    # Side performance
    long_side = _side_performance([t for t in trades if t.direction == "long"])
    short_side = _side_performance([t for t in trades if t.direction == "short"])

    # Monthly returns
    monthly = _monthly_returns(equity_curve, candles)

    # Drawdown curve
    drawdown_curve = _drawdown_curve(equity_curve)

    # Sharpe & Sortino
    sharpe = _sharpe(equity_curve, candles)
    sortino = _sortino(equity_curve, candles)

    # Compliance
    from app.engine.compliance import check_compliance
    compliance = check_compliance(dd_pct, "futures")

    return BacktestResult(
        strategy_id=strategy_id,
        risk_pct=risk_pct,
        initial_capital=initial_capital,
        total_return_pct=total_return_pct,
        net_profit_dollars=net_profit,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        win_rate=win_rate,
        avg_r_multiple=avg_r,
        total_trades=len(trades),
        max_drawdown_pct=dd_pct,
        max_drawdown_dollars=dd_dollars,
        best_trade=best_trade,
        worst_trade=worst_trade,
        long_side_performance=long_side,
        short_side_performance=short_side,
        monthly_returns=monthly,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        compliance_status=compliance["status"],
        compliance_reason=compliance["reason"],
        trades=trades,
    )


# ---------------------------------------------------------------------------
# Metric helpers (duplicated from backtester to keep ORB self-contained)
# ---------------------------------------------------------------------------

def _max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    if not equity_curve:
        return 0.0, 0.0
    peak = equity_curve[0]
    max_dd_pct = 0.0
    max_dd_dollars = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd_pct = (peak - val) / peak if peak > 0 else 0.0
        dd_dollars = peak - val
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_dollars = dd_dollars
    return max_dd_pct, max_dd_dollars


def _drawdown_curve(equity_curve: list[float]) -> list[float]:
    if not equity_curve:
        return []
    peak = equity_curve[0]
    dd = []
    for val in equity_curve:
        if val > peak:
            peak = val
        dd.append((peak - val) / peak if peak > 0 else 0.0)
    return dd


def _side_performance(trades: list[Trade]) -> dict:
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "gross_profit": 0, "gross_loss": 0, "net_pnl": 0, "avg_r_multiple": 0}
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 4),
        "gross_profit": round(sum(t.pnl for t in wins), 2),
        "gross_loss": round(abs(sum(t.pnl for t in losses)), 2),
        "net_pnl": round(sum(t.pnl for t in trades), 2),
        "avg_r_multiple": round(sum(t.r_multiple for t in trades) / len(trades), 4),
    }


def _monthly_returns(equity_curve: list[float], candles: list[Candle]) -> list[dict]:
    if not equity_curve or not candles:
        return []
    month_equity: dict[str, list[float]] = defaultdict(list)
    for i, c in enumerate(candles):
        if i >= len(equity_curve):
            break
        month = datetime.fromtimestamp(c.ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        month_equity[month].append(equity_curve[i])
    if len(month_equity) < 2:
        return []
    results = []
    sorted_months = sorted(month_equity.keys())
    for j in range(1, len(sorted_months)):
        prev = month_equity[sorted_months[j - 1]][-1]
        curr = month_equity[sorted_months[j]][-1]
        ret_pct = (curr - prev) / prev if prev > 0 else 0.0
        ret_dollars = curr - prev
        results.append({"month": sorted_months[j], "return_pct": round(ret_pct, 6), "return_dollars": round(ret_dollars, 2)})
    return results


def _daily_returns(equity_curve: list[float], candles: list[Candle]) -> tuple[np.ndarray, float]:
    if not equity_curve or len(equity_curve) < 2:
        return np.array([]), math.sqrt(252)
    day_equity: dict[str, float] = {}
    for i, c in enumerate(candles):
        if i >= len(equity_curve):
            break
        day = datetime.fromtimestamp(c.ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        day_equity[day] = equity_curve[i]
    if len(day_equity) < 2:
        eq = np.array(equity_curve)
        return np.diff(eq) / eq[:-1], math.sqrt(252)
    sorted_vals = [v for _, v in sorted(day_equity.items())]
    eq = np.array(sorted_vals)
    returns = np.diff(eq) / eq[:-1]
    returns = returns[np.isfinite(returns)]
    return returns, math.sqrt(252)


def _sharpe(equity_curve: list[float], candles: list[Candle]) -> float:
    returns, annualise = _daily_returns(equity_curve, candles)
    if len(returns) < 2:
        return 0.0
    std = np.std(returns, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(returns) / std * annualise)


def _sortino(equity_curve: list[float], candles: list[Candle]) -> float:
    returns, annualise = _daily_returns(equity_curve, candles)
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0:
        return float("inf") if np.mean(returns) > 0 else 0.0
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return 0.0
    return float(np.mean(returns) / downside_std * annualise)
