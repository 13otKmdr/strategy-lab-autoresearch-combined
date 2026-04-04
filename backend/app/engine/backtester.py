"""
Bar-by-bar backtesting simulation engine for futures day trading.

Adapted from agent-network/backtesting/engine.py.
Tests each strategy at specified risk levels (0.25%, 0.5%).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from app.config import COMMISSION_FLAT, COMMISSION_PCT, SLIPPAGE_PCT, WARMUP_BARS
from app.models.backtest import BacktestResult, Trade
from app.models.market import Candle
from app.models.strategy import StrategyDefinition
from app.engine.signals import (
    calc_stop_price, calc_take_profit_price, check_entry,
    compute_indicators, is_short_trigger,
)
from app.engine.indicators import ema as _ema


def run_backtest(
    strategy: StrategyDefinition,
    candles: list[Candle],
    risk_pct: float,
    initial_capital: float,
    market_type: str = "futures",
) -> BacktestResult:
    """Run a full backtest and return a complete BacktestResult."""
    indicators = compute_indicators(strategy, candles)
    trades, equity_curve = _simulate(strategy, candles, indicators, risk_pct, initial_capital)

    # Compute all metrics
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
    compliance = check_compliance(dd_pct, market_type)

    return BacktestResult(
        strategy_id=strategy.strategy_id,
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


def _simulate(
    strategy: StrategyDefinition,
    candles: list[Candle],
    indicators: dict,
    risk_pct: float,
    initial_capital: float,
) -> tuple[list[Trade], list[float]]:
    n = len(candles)
    if n < WARMUP_BARS + 2:
        return [], [initial_capital] * n

    equity = initial_capital
    equity_curve = [initial_capital] * n

    max_positions = int(strategy.risk.get("max_open_positions", 1))
    time_exit_bars = strategy.exit.get("time_exit_bars")
    trailing_atr_mult = strategy.exit.get("trailing_stop_atr")

    trigger_name = strategy.entry.get("trigger", "")
    short = is_short_trigger(trigger_name)
    direction = "short" if short else "long"

    close_arr = np.array([c.close for c in candles])
    regime_arr = _compute_regimes(indicators["ema200"], close_arr)

    open_positions: list[dict] = []
    completed_trades: list[Trade] = []

    for i in range(WARMUP_BARS, n):
        bar_close = candles[i].close

        # Check exits
        still_open = []
        for pos in open_positions:
            trade = _check_exit(pos, candles, indicators, i, time_exit_bars, trailing_atr_mult, equity)
            if trade is not None:
                equity += trade.pnl
                completed_trades.append(trade)
            else:
                if trailing_atr_mult and not math.isnan(indicators["atr"][i]):
                    atr_val = indicators["atr"][i]
                    if short:
                        new_trail = bar_close + trailing_atr_mult * atr_val
                        pos["trailing_stop"] = min(pos.get("trailing_stop", math.inf), new_trail)
                    else:
                        new_trail = bar_close - trailing_atr_mult * atr_val
                        pos["trailing_stop"] = max(pos.get("trailing_stop", 0), new_trail)
                still_open.append(pos)
        open_positions = still_open

        # Check entry
        if len(open_positions) < max_positions and check_entry(strategy, indicators, i):
            entry_price = bar_close * (1 - SLIPPAGE_PCT) if short else bar_close * (1 + SLIPPAGE_PCT)
            stop_price = calc_stop_price(strategy, entry_price, indicators, i, short=short)

            invalid_stop = (stop_price <= entry_price) if short else (stop_price >= entry_price)
            if invalid_stop or stop_price <= 0:
                equity_curve[i] = equity
                continue

            risk_usd = equity * (risk_pct / 100.0)
            risk_dist = abs(entry_price - stop_price)
            size = risk_usd / risk_dist if risk_dist > 0 else 0
            if size <= 0:
                equity_curve[i] = equity
                continue

            cost = _commission(entry_price * size)
            equity -= cost

            tp_price = calc_take_profit_price(strategy, entry_price, stop_price, short=short)
            trail_stop = None
            if trailing_atr_mult and not math.isnan(indicators["atr"][i]):
                atr_val = indicators["atr"][i]
                trail_stop = (entry_price + trailing_atr_mult * atr_val if short
                              else entry_price - trailing_atr_mult * atr_val)

            open_positions.append({
                "entry_bar": i,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "tp_price": tp_price,
                "trailing_stop": trail_stop,
                "size": size,
                "risk_usd": risk_usd,
                "regime": regime_arr[i],
                "entry_ts": candles[i].ts,
                "direction": direction,
            })

        equity_curve[i] = equity

    # Force-close any remaining open positions
    for pos in open_positions:
        pos_short = pos.get("direction") == "short"
        exit_price = candles[-1].close * (1 + SLIPPAGE_PCT if pos_short else 1 - SLIPPAGE_PCT)
        cost = _commission(exit_price * pos["size"])
        gross_pnl = ((pos["entry_price"] - exit_price) * pos["size"] if pos_short
                     else (exit_price - pos["entry_price"]) * pos["size"])
        net_pnl = gross_pnl - cost
        equity += net_pnl
        equity_curve[-1] = equity
        completed_trades.append(Trade(
            entry_bar=pos["entry_bar"], exit_bar=n - 1,
            entry_price=pos["entry_price"], exit_price=exit_price,
            size=pos["size"], direction=pos.get("direction", "long"),
            pnl=net_pnl,
            pnl_pct=net_pnl / (pos["entry_price"] * pos["size"]) if pos["entry_price"] * pos["size"] > 0 else 0,
            r_multiple=net_pnl / pos["risk_usd"] if pos["risk_usd"] > 0 else 0,
            exit_reason="end_of_data",
            entry_ts=pos["entry_ts"], exit_ts=candles[-1].ts,
            regime=pos["regime"],
        ))

    return completed_trades, equity_curve


def _check_exit(pos, candles, indicators, i, time_exit_bars, trailing_atr_mult, equity):
    low = candles[i].low
    high = candles[i].high
    close = candles[i].close
    short = pos.get("direction") == "short"

    exit_price = None
    exit_reason = None

    if short:
        if high >= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 + SLIPPAGE_PCT), "stop_loss"
        elif low <= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 + SLIPPAGE_PCT), "take_profit"
        elif pos.get("trailing_stop") and high >= pos["trailing_stop"]:
            exit_price, exit_reason = pos["trailing_stop"] * (1 + SLIPPAGE_PCT), "trailing_stop"
        elif time_exit_bars and (i - pos["entry_bar"]) >= time_exit_bars:
            exit_price, exit_reason = close * (1 + SLIPPAGE_PCT), "time_exit"
    else:
        if low <= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 - SLIPPAGE_PCT), "stop_loss"
        elif high >= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 - SLIPPAGE_PCT), "take_profit"
        elif pos.get("trailing_stop") and low <= pos["trailing_stop"]:
            exit_price, exit_reason = pos["trailing_stop"] * (1 - SLIPPAGE_PCT), "trailing_stop"
        elif time_exit_bars and (i - pos["entry_bar"]) >= time_exit_bars:
            exit_price, exit_reason = close * (1 - SLIPPAGE_PCT), "time_exit"

    if exit_price is None:
        return None

    cost = _commission(exit_price * pos["size"])
    gross_pnl = ((pos["entry_price"] - exit_price) * pos["size"] if short
                 else (exit_price - pos["entry_price"]) * pos["size"])
    net_pnl = gross_pnl - cost

    return Trade(
        entry_bar=pos["entry_bar"], exit_bar=i,
        entry_price=pos["entry_price"], exit_price=exit_price,
        size=pos["size"], direction=pos.get("direction", "long"),
        pnl=net_pnl,
        pnl_pct=net_pnl / (pos["entry_price"] * pos["size"]) if pos["entry_price"] * pos["size"] > 0 else 0,
        r_multiple=net_pnl / pos["risk_usd"] if pos["risk_usd"] > 0 else 0,
        exit_reason=exit_reason,
        entry_ts=pos["entry_ts"], exit_ts=candles[i].ts,
        regime=pos["regime"],
    )


def _commission(trade_value: float) -> float:
    return max(COMMISSION_FLAT, trade_value * COMMISSION_PCT)


def _compute_regimes(ema200: np.ndarray, close: np.ndarray) -> list[str]:
    n = len(close)
    regimes = ["sideways"] * n
    for i in range(5, n):
        e = ema200[i]
        if math.isnan(e):
            continue
        e_prev = ema200[i - 5]
        if math.isnan(e_prev):
            continue
        if close[i] > e and e > e_prev:
            regimes[i] = "bull"
        elif close[i] < e and e < e_prev:
            regimes[i] = "bear"
    return regimes


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
    # Futures: ~252 trading days/year
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
