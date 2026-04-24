"""
VWAP Mean Reversion backtester.

Institutional traders benchmark to VWAP, so price structurally reverts —
especially during low-momentum midday sessions (11:00-14:30 ET).

Entry: price extends > threshold ATR from VWAP, then starts reverting.
Stop:  beyond the extreme + buffer ATR.
TP:    VWAP level, or R-multiple of risk.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from app.config import (
    COMMISSION_FLAT,
    COMMISSION_PCT,
    INITIAL_CAPITAL,
    SLIPPAGE_PCT,
    WARMUP_BARS,
)
from app.engine.backtester import (
    _commission,
    _drawdown_curve,
    _max_drawdown,
    _monthly_returns,
    _sharpe,
    _side_performance,
    _sortino,
)
from app.engine.compliance import check_compliance
from app.engine.indicators import atr as calc_atr
from app.engine.indicators import vwap as calc_vwap
from app.engine.prop_risk_sizing import PropRiskSizingInput, futures_position_pnl, size_integer_micro_contracts
from app.models.backtest import BacktestResult, Trade
from app.models.market import Candle
from app.models.strategy import StrategyDefinition


# ---------------------------------------------------------------------------
# Session filter helpers
# ---------------------------------------------------------------------------

def _hour_minute_et(ts_ms: int) -> tuple[int, int]:
    """Return (hour, minute) in US/Eastern approximation (UTC-4)."""
    utc_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    et_hour = (utc_dt.hour - 4) % 24
    return et_hour, utc_dt.minute


def _in_midday_session(ts_ms: int) -> bool:
    """True if candle falls within 11:00-14:30 ET."""
    h, m = _hour_minute_et(ts_ms)
    if h < 11:
        return False
    if h > 14:
        return False
    if h == 14 and m > 30:
        return False
    return True


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def run_vwap_backtest(
    candles: list[Candle],
    *,
    distance_threshold_atr: float = 2.0,
    direction: str = "both",          # "long" | "short" | "both"
    stop_buffer_atr: float = 1.0,
    tp_mode: str = "vwap",            # "vwap" | "r_multiple_2" | "r_multiple_3"
    session_filter: str = "midday_only",  # "midday_only" | "all_day"
    risk_pct: float = 0.5,
    initial_capital: float = INITIAL_CAPITAL,
    strategy_id: str = "",
    market_type: str = "futures",
    symbol: str = "MYM",
) -> BacktestResult:
    """Run a VWAP mean-reversion backtest and return a BacktestResult."""
    n = len(candles)

    # Build numpy arrays
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    closes = np.array([c.close for c in candles])
    volumes = np.array([c.volume for c in candles])

    # Indicators
    vwap_arr = calc_vwap(highs, lows, closes, volumes)
    atr_arr = calc_atr(highs, lows, closes, period=14)

    if n < WARMUP_BARS + 2:
        return _empty_result(strategy_id, risk_pct, initial_capital, n, candles)

    equity = initial_capital
    equity_curve = [initial_capital] * n

    open_positions: list[dict] = []
    completed_trades: list[Trade] = []

    # Track "extending" state per direction for reversion detection
    prev_dist = 0.0  # signed distance: positive = above VWAP, negative = below

    for i in range(WARMUP_BARS, n):
        cur_close = candles[i].close
        cur_vwap = vwap_arr[i]
        cur_atr = atr_arr[i]

        if math.isnan(cur_vwap) or math.isnan(cur_atr) or cur_atr <= 0:
            equity_curve[i] = equity
            prev_dist = 0.0
            continue

        signed_dist = cur_close - cur_vwap  # positive = above VWAP
        dist_in_atr = abs(signed_dist) / cur_atr

        # --- Check exits first ---
        still_open = []
        for pos in open_positions:
            trade = _check_exit(pos, candles, vwap_arr, i, equity)
            if trade is not None:
                equity += trade.pnl
                completed_trades.append(trade)
            else:
                still_open.append(pos)
        open_positions = still_open

        # --- Check entry ---
        if len(open_positions) < 1:
            # Session filter
            if session_filter == "midday_only" and not _in_midday_session(candles[i].ts):
                equity_curve[i] = equity
                prev_dist = signed_dist
                continue

            # Need threshold distance AND reversion signal
            if dist_in_atr >= distance_threshold_atr and prev_dist != 0.0:
                # Detect reversion: was extending, now reverting
                reverting_long = (
                    signed_dist < 0
                    and signed_dist > prev_dist  # was more negative, now less
                )
                reverting_short = (
                    signed_dist > 0
                    and signed_dist < prev_dist  # was more positive, now less
                )

                take_long = reverting_long and direction in ("long", "both")
                take_short = reverting_short and direction in ("short", "both")

                if take_long:
                    _try_enter(
                        "long", candles, i, cur_close, cur_vwap, cur_atr,
                        stop_buffer_atr, tp_mode, risk_pct, equity,
                        open_positions, strategy_id, symbol,
                    )
                elif take_short:
                    _try_enter(
                        "short", candles, i, cur_close, cur_vwap, cur_atr,
                        stop_buffer_atr, tp_mode, risk_pct, equity,
                        open_positions, strategy_id, symbol,
                    )

        equity_curve[i] = equity
        prev_dist = signed_dist

    # Force-close remaining positions
    for pos in open_positions:
        is_short = pos["direction"] == "short"
        exit_price = candles[-1].close * (1 + SLIPPAGE_PCT if is_short else 1 - SLIPPAGE_PCT)
        cost = _commission(pos["size"])
        gross_pnl = futures_position_pnl(pos.get("symbol", "MYM"), pos["entry_price"], exit_price, pos["size"], pos["direction"])
        net_pnl = gross_pnl - pos.get("entry_cost", 0.0) - cost
        equity += net_pnl
        equity_curve[-1] = equity
        completed_trades.append(Trade(
            entry_bar=pos["entry_bar"], exit_bar=n - 1,
            entry_price=pos["entry_price"], exit_price=exit_price,
            size=pos["size"], direction=pos["direction"],
            pnl=net_pnl,
            pnl_pct=net_pnl / (pos["entry_price"] * pos["size"]) if pos["entry_price"] * pos["size"] > 0 else 0,
            r_multiple=net_pnl / pos["risk_usd"] if pos["risk_usd"] > 0 else 0,
            exit_reason="end_of_data",
            entry_ts=pos["entry_ts"], exit_ts=candles[-1].ts,
        ))

    return _build_result(strategy_id, risk_pct, initial_capital, completed_trades, equity_curve, candles, market_type)


# ---------------------------------------------------------------------------
# Entry helper
# ---------------------------------------------------------------------------

def _try_enter(
    side: str,
    candles: list[Candle],
    i: int,
    cur_close: float,
    cur_vwap: float,
    cur_atr: float,
    stop_buffer_atr: float,
    tp_mode: str,
    risk_pct: float,
    equity: float,
    open_positions: list[dict],
    strategy_id: str,
    symbol: str = "MYM",
) -> None:
    is_short = side == "short"

    entry_price = cur_close * (1 - SLIPPAGE_PCT if is_short else 1 + SLIPPAGE_PCT)

    # Stop: beyond the recent extreme + buffer ATR
    if is_short:
        # Short entry above VWAP — stop above the high + buffer
        extreme = candles[i].high
        stop_price = extreme + stop_buffer_atr * cur_atr
    else:
        # Long entry below VWAP — stop below the low - buffer
        extreme = candles[i].low
        stop_price = extreme - stop_buffer_atr * cur_atr

    # Validate stop
    if is_short and stop_price <= entry_price:
        return
    if not is_short and stop_price >= entry_price:
        return
    if stop_price <= 0:
        return

    risk_dist = abs(entry_price - stop_price)
    if risk_dist <= 0:
        return
    sizing = size_integer_micro_contracts(PropRiskSizingInput(
        symbol=symbol,
        entry_price=entry_price,
        stop_price=stop_price,
        risk_level=risk_pct,
    ))
    if sizing.contracts <= 0:
        return
    size = sizing.contracts
    risk_usd = sizing.contracts * sizing.dollars_at_risk_per_contract

    # Take profit
    if tp_mode == "vwap":
        tp_price = cur_vwap
    elif tp_mode == "r_multiple_2":
        tp_price = entry_price - 2 * risk_dist if is_short else entry_price + 2 * risk_dist
    elif tp_mode == "r_multiple_3":
        tp_price = entry_price - 3 * risk_dist if is_short else entry_price + 3 * risk_dist
    else:
        tp_price = cur_vwap

    # Validate TP direction
    if is_short and tp_price >= entry_price:
        return
    if not is_short and tp_price <= entry_price:
        return

    cost = _commission(size)

    open_positions.append({
        "entry_bar": i,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "tp_price": tp_price,
        "size": size,
        "symbol": symbol,
        "entry_cost": cost,
        "risk_usd": risk_usd,
        "direction": side,
        "entry_ts": candles[i].ts,
    })


# ---------------------------------------------------------------------------
# Exit helper
# ---------------------------------------------------------------------------

def _check_exit(
    pos: dict,
    candles: list[Candle],
    vwap_arr: np.ndarray,
    i: int,
    equity: float,
) -> Trade | None:
    high = candles[i].high
    low = candles[i].low
    close = candles[i].close
    is_short = pos["direction"] == "short"

    exit_price = None
    exit_reason = None

    if is_short:
        if high >= pos["stop_price"]:
            exit_price = pos["stop_price"] * (1 + SLIPPAGE_PCT)
            exit_reason = "stop_loss"
        elif low <= pos["tp_price"]:
            exit_price = pos["tp_price"] * (1 + SLIPPAGE_PCT)
            exit_reason = "take_profit"
    else:
        if low <= pos["stop_price"]:
            exit_price = pos["stop_price"] * (1 - SLIPPAGE_PCT)
            exit_reason = "stop_loss"
        elif high >= pos["tp_price"]:
            exit_price = pos["tp_price"] * (1 - SLIPPAGE_PCT)
            exit_reason = "take_profit"

    if exit_price is None:
        return None

    cost = _commission(pos["size"])
    gross_pnl = futures_position_pnl(pos.get("symbol", "MYM"), pos["entry_price"], exit_price, pos["size"], pos["direction"])
    net_pnl = gross_pnl - pos.get("entry_cost", 0.0) - cost

    return Trade(
        entry_bar=pos["entry_bar"], exit_bar=i,
        entry_price=pos["entry_price"], exit_price=exit_price,
        size=pos["size"], direction=pos["direction"],
        pnl=net_pnl,
        pnl_pct=net_pnl / (pos["entry_price"] * pos["size"]) if pos["entry_price"] * pos["size"] > 0 else 0,
        r_multiple=net_pnl / pos["risk_usd"] if pos["risk_usd"] > 0 else 0,
        exit_reason=exit_reason,
        entry_ts=pos["entry_ts"], exit_ts=candles[i].ts,
    )


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------

def _build_result(
    strategy_id: str,
    risk_pct: float,
    initial_capital: float,
    trades: list[Trade],
    equity_curve: list[float],
    candles: list[Candle],
    market_type: str,
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

    dd_pct, dd_dollars = _max_drawdown(equity_curve)

    long_side = _side_performance([t for t in trades if t.direction == "long"])
    short_side = _side_performance([t for t in trades if t.direction == "short"])

    monthly = _monthly_returns(equity_curve, candles)
    drawdown_crv = _drawdown_curve(equity_curve)
    sharpe = _sharpe(equity_curve, candles)
    sortino = _sortino(equity_curve, candles)

    compliance = check_compliance(dd_pct, market_type)

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
        drawdown_curve=drawdown_crv,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        compliance_status=compliance["status"],
        compliance_reason=compliance["reason"],
        trades=trades,
    )


def _empty_result(
    strategy_id: str,
    risk_pct: float,
    initial_capital: float,
    n: int,
    candles: list[Candle],
) -> BacktestResult:
    eq = [initial_capital] * max(n, 1)
    return _build_result(strategy_id, risk_pct, initial_capital, [], eq, candles, "futures")


# ---------------------------------------------------------------------------
# Strategy generation
# ---------------------------------------------------------------------------

def generate_vwap_strategies(instrument: str, n: int = 30) -> list[StrategyDefinition]:
    """Generate a matrix of VWAP mean-reversion strategy variations."""
    distance_thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]
    directions = ["long", "short", "both"]
    stop_buffers = [0.5, 1.0]
    tp_modes = ["vwap", "r_multiple_2", "r_multiple_3"]
    session_filters = ["midday_only", "all_day"]

    strategies: list[StrategyDefinition] = []

    for dist in distance_thresholds:
        for dirn in directions:
            for stop_buf in stop_buffers:
                for tp in tp_modes:
                    for sess in session_filters:
                        sid = f"vwap_rev_{instrument}_{uuid.uuid4().hex[:8]}"
                        name = f"VWAP Rev {dirn} dist={dist} stop={stop_buf} tp={tp} sess={sess}"

                        strategies.append(StrategyDefinition(
                            strategy_id=sid,
                            strategy_name=name,
                            strategy_type="mean_reversion",
                            market_type="futures",
                            thesis_summary=(
                                f"VWAP mean reversion: enter {dirn} when price is >{dist} ATR "
                                f"from VWAP and starts reverting. Stop buffer {stop_buf} ATR, "
                                f"TP mode {tp}, session {sess}."
                            ),
                            indicators_used=[
                                {"type": "VWAP", "params": {}},
                                {"type": "ATR", "params": {"period": 14}},
                            ],
                            candlestick_patterns_used=[],
                            timeframe_stack=["15m"],
                            entry_rules={
                                "trigger": "VWAP_REVERSION",
                                "distance_threshold_atr": dist,
                                "direction": dirn,
                                "description": f"Price >{dist} ATR from VWAP and reverting",
                            },
                            exit_rules={
                                "stop_loss": {"type": "extreme_plus_buffer", "buffer_atr": stop_buf},
                                "take_profit": {"type": tp},
                            },
                            stop_loss_logic={"type": "extreme_plus_buffer_atr", "value": stop_buf},
                            take_profit_logic={"type": tp, "value": 2.0 if tp == "r_multiple_2" else 3.0 if tp == "r_multiple_3" else 0.0},
                            trailing_stop_or_break_even_logic={},
                            session_filters={
                                "allowed_sessions": ["midday"] if sess == "midday_only" else ["all"],
                                "session_filter": sess,
                            },
                            volatility_filters={},
                            fundamental_filters_if_any={},
                            intended_asset_classes=[instrument],
                            primary_indicator={"type": "VWAP", "params": {}},
                            confirmation_indicator={"type": "ATR", "params": {"period": 14}},
                            entry={
                                "trigger": "VWAP_REVERSION",
                                "distance_threshold_atr": dist,
                                "direction": dirn,
                            },
                            exit={
                                "stop_buffer_atr": stop_buf,
                                "tp_mode": tp,
                            },
                            risk={"max_open_positions": 1},
                        ))

                        if len(strategies) >= n:
                            return strategies

    return strategies[:n]
