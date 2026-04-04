"""
Session Rotation Engine — rotates strategy types based on trading session.

Morning (9:30-10:30 ET): breakout strategies (high volatility at open)
Midday (10:30-14:00 ET): mean reversion strategies (range-bound chop)
Afternoon (14:00-16:00 ET): momentum/trend strategies (institutional flow)
Overnight: no trading by default
"""
from __future__ import annotations

import itertools
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import numpy as np

from app.config import (
    COMMISSION_FLAT, COMMISSION_PCT, INITIAL_CAPITAL, SLIPPAGE_PCT, WARMUP_BARS,
)
from app.engine.compliance import check_compliance
from app.engine.indicators import ema as _ema
from app.engine.signals import (
    CONFIRMATIONS, ENTRY_TRIGGERS, calc_stop_price, calc_take_profit_price,
    check_entry, compute_indicators, is_short_trigger,
)
from app.models.backtest import BacktestResult, Trade
from app.models.market import Candle
from app.models.strategy import StrategyDefinition

# ── UTC offsets for ET sessions ──────────────────────────────────────────────
# ET is UTC-5 (EST) or UTC-4 (EDT).  For simplicity we use a fixed UTC-4 (EDT)
# offset since the majority of the trading year falls in EDT, and ETF proxy data
# from Twelve Data only covers regular market hours (9:30-16:00 ET) anyway.
_ET_OFFSET = timedelta(hours=-4)
_ET_TZ = timezone(_ET_OFFSET)


def classify_session(ts_ms: int) -> str:
    """Classify a Unix-ms timestamp into a trading session.

    Returns one of: "morning", "midday", "afternoon", "overnight".
    """
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=_ET_TZ)
    minutes_since_midnight = dt.hour * 60 + dt.minute

    morning_start = 9 * 60 + 30   # 09:30
    midday_start = 10 * 60 + 30   # 10:30
    afternoon_start = 14 * 60     # 14:00
    market_close = 16 * 60        # 16:00

    if morning_start <= minutes_since_midnight < midday_start:
        return "morning"
    elif midday_start <= minutes_since_midnight < afternoon_start:
        return "midday"
    elif afternoon_start <= minutes_since_midnight < market_close:
        return "afternoon"
    else:
        return "overnight"


# ── Session-specific trigger/filter mappings ─────────────────────────────────

# Strategy types and their typical trigger/filter combos
SESSION_STRATEGY_MAP: dict[str, list[dict]] = {
    "breakout": [
        {"trigger": "DC_UPPER_BREAK", "filter": "ATR_EXPANDING",
         "primary": {"type": "DONCHIAN", "params": {"period": 20}},
         "confirmation": {"type": "ATR", "params": {"period": 14}}},
        {"trigger": "BB_LOWER_TOUCH", "filter": "VOLUME_ABOVE_SMA",
         "primary": {"type": "BB", "params": {"period": 20, "std_dev": 2.0}},
         "confirmation": {"type": "VOLUME", "params": {"period": 20}}},
        {"trigger": "KC_LOWER_TOUCH", "filter": "ATR_EXPANDING",
         "primary": {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}},
         "confirmation": {"type": "ATR", "params": {"period": 14}}},
    ],
    "mean_reversion": [
        {"trigger": "RSI_OVERSOLD", "filter": "PRICE_ABOVE_EMA",
         "primary": {"type": "RSI", "params": {"period": 14}},
         "confirmation": {"type": "EMA", "params": {"period": 50}}},
        {"trigger": "BB_LOWER_TOUCH", "filter": "NONE",
         "primary": {"type": "BB", "params": {"period": 20, "std_dev": 2.0}},
         "confirmation": {"type": "EMA", "params": {"period": 50}}},
        {"trigger": "STOCH_OVERSOLD", "filter": "PRICE_ABOVE_EMA",
         "primary": {"type": "STOCH", "params": {"k_period": 14, "d_period": 3}},
         "confirmation": {"type": "EMA", "params": {"period": 50}}},
        {"trigger": "CCI_OVERSOLD", "filter": "NONE",
         "primary": {"type": "CCI", "params": {"period": 20}},
         "confirmation": {"type": "EMA", "params": {"period": 50}}},
    ],
    "momentum": [
        {"trigger": "MACD_CROSS_ABOVE", "filter": "ADX_TRENDING",
         "primary": {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
         "confirmation": {"type": "ADX", "params": {"period": 14}}},
        {"trigger": "ROC_CROSS_ABOVE", "filter": "VOLUME_ABOVE_SMA",
         "primary": {"type": "ROC", "params": {"period": 12}},
         "confirmation": {"type": "VOLUME", "params": {"period": 20}}},
        {"trigger": "PRICE_ABOVE_EMA", "filter": "ADX_TRENDING",
         "primary": {"type": "EMA", "params": {"period": 20}},
         "confirmation": {"type": "ADX", "params": {"period": 14}}},
    ],
    "trend_following": [
        {"trigger": "PRICE_ABOVE_EMA", "filter": "ADX_TRENDING",
         "primary": {"type": "EMA", "params": {"period": 20}},
         "confirmation": {"type": "ADX", "params": {"period": 14}}},
        {"trigger": "MACD_CROSS_ABOVE", "filter": "VOLUME_ABOVE_SMA",
         "primary": {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
         "confirmation": {"type": "VOLUME", "params": {"period": 20}}},
        {"trigger": "PRICE_ABOVE_CLOUD", "filter": "ATR_EXPANDING",
         "primary": {"type": "ICHIMOKU", "params": {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}},
         "confirmation": {"type": "ATR", "params": {"period": 14}}},
        {"trigger": "VWAP_CROSS_ABOVE", "filter": "OBV_RISING",
         "primary": {"type": "VWAP", "params": {}},
         "confirmation": {"type": "OBV", "params": {}}},
    ],
}


# ── Config dataclass ─────────────────────────────────────────────────────────

@dataclass
class SessionRotationConfig:
    """Configuration for session-rotated backtesting."""
    # Strategy types per session
    morning_strategy_type: str = "breakout"
    midday_strategy_type: str = "mean_reversion"
    afternoon_strategy_type: str = "momentum"

    # Trigger/filter pairs per session (indices into SESSION_STRATEGY_MAP lists)
    morning_trigger: str = "DC_UPPER_BREAK"
    morning_filter: str = "ATR_EXPANDING"
    morning_primary: dict = field(default_factory=lambda: {"type": "DONCHIAN", "params": {"period": 20}})
    morning_confirmation: dict = field(default_factory=lambda: {"type": "ATR", "params": {"period": 14}})

    midday_trigger: str = "RSI_OVERSOLD"
    midday_filter: str = "PRICE_ABOVE_EMA"
    midday_primary: dict = field(default_factory=lambda: {"type": "RSI", "params": {"period": 14}})
    midday_confirmation: dict = field(default_factory=lambda: {"type": "EMA", "params": {"period": 50}})

    afternoon_trigger: str = "MACD_CROSS_ABOVE"
    afternoon_filter: str = "ADX_TRENDING"
    afternoon_primary: dict = field(default_factory=lambda: {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}})
    afternoon_confirmation: dict = field(default_factory=lambda: {"type": "ADX", "params": {"period": 14}})

    # Daily loss limit (absolute $)
    daily_loss_limit: float = 500.0  # 1% of $50K

    # Common stop/TP settings
    stop_loss_type: str = "atr_multiple"
    stop_loss_value: float = 2.0
    take_profit_type: str = "r_multiple"
    take_profit_value: float = 2.0
    trailing_stop_atr: float | None = None
    time_exit_bars: int | None = 48


# ── Backtest engine ──────────────────────────────────────────────────────────

def run_session_backtest(
    config: SessionRotationConfig,
    candles: list[Candle],
    risk_pct: float = 0.5,
    initial_capital: float = INITIAL_CAPITAL,
) -> BacktestResult:
    """Run a session-rotation backtest across the provided candles.

    At each bar the session is classified and the corresponding trigger/filter
    is used to evaluate entry signals.  A daily loss limit circuit-breaker
    halts all trading for the rest of a day once the threshold is hit.
    """
    n = len(candles)
    if n < WARMUP_BARS + 2:
        return _empty_result(config, risk_pct, initial_capital, n)

    # Pre-compute indicators for every session's strategy config
    session_indicators = _compute_all_session_indicators(config, candles)

    # Build helper arrays
    close_arr = np.array([c.close for c in candles])
    ema200 = _ema(close_arr, 200)
    regime_arr = _compute_regimes(ema200, close_arr)

    equity = initial_capital
    equity_curve = [initial_capital] * n
    open_positions: list[dict] = []
    completed_trades: list[Trade] = []

    # Daily P&L tracking
    daily_pnl: dict[str, float] = defaultdict(float)  # date_str -> cumulative P&L
    daily_locked: set[str] = set()  # dates where trading is halted

    for i in range(WARMUP_BARS, n):
        bar_ts = candles[i].ts
        session = classify_session(bar_ts)
        day_key = datetime.fromtimestamp(bar_ts / 1000, tz=_ET_TZ).strftime("%Y-%m-%d")

        # ── Check exits first ────────────────────────────────────────────
        still_open = []
        for pos in open_positions:
            trade = _check_exit(pos, candles, i, config, equity)
            if trade is not None:
                equity += trade.pnl
                completed_trades.append(trade)
                daily_pnl[day_key] += trade.pnl
                # Check daily loss limit
                if daily_pnl[day_key] <= -config.daily_loss_limit:
                    daily_locked.add(day_key)
            else:
                # Update trailing stop
                if config.trailing_stop_atr and pos.get("indicators"):
                    atr_val = pos["indicators"]["atr"][i]
                    if not math.isnan(atr_val):
                        bar_close = candles[i].close
                        is_short = pos["direction"] == "short"
                        if is_short:
                            new_trail = bar_close + config.trailing_stop_atr * atr_val
                            pos["trailing_stop"] = min(pos.get("trailing_stop", math.inf), new_trail)
                        else:
                            new_trail = bar_close - config.trailing_stop_atr * atr_val
                            pos["trailing_stop"] = max(pos.get("trailing_stop", 0), new_trail)
                still_open.append(pos)
        open_positions = still_open

        # ── Check entry ──────────────────────────────────────────────────
        # Skip overnight and locked days
        if session == "overnight" or day_key in daily_locked:
            equity_curve[i] = equity
            continue

        if len(open_positions) >= 1:
            equity_curve[i] = equity
            continue

        # Get session-specific trigger/filter/indicators
        trigger_name, filter_name, indicators = _session_signal_params(config, session, session_indicators)
        trigger_fn = ENTRY_TRIGGERS.get(trigger_name)
        confirm_fn = CONFIRMATIONS.get(filter_name, CONFIRMATIONS["NONE"])

        if trigger_fn is None:
            equity_curve[i] = equity
            continue

        # Evaluate signal
        try:
            signal = trigger_fn(indicators, i) and confirm_fn(indicators, i)
        except (IndexError, ZeroDivisionError):
            signal = False

        if not signal:
            equity_curve[i] = equity
            continue

        short = is_short_trigger(trigger_name)
        direction = "short" if short else "long"
        bar_close = candles[i].close
        entry_price = bar_close * (1 - SLIPPAGE_PCT) if short else bar_close * (1 + SLIPPAGE_PCT)

        # Build a lightweight strategy object for stop/TP calculation
        tmp_strategy = _tmp_strategy(config)
        stop_price = calc_stop_price(tmp_strategy, entry_price, indicators, i, short=short)

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

        tp_price = calc_take_profit_price(tmp_strategy, entry_price, stop_price, short=short)
        trail_stop = None
        if config.trailing_stop_atr and not math.isnan(indicators["atr"][i]):
            atr_val = indicators["atr"][i]
            trail_stop = (entry_price + config.trailing_stop_atr * atr_val if short
                          else entry_price - config.trailing_stop_atr * atr_val)

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
            "indicators": indicators,
            "session": session,
        })

        equity_curve[i] = equity

    # Force-close remaining positions
    for pos in open_positions:
        is_short = pos["direction"] == "short"
        exit_price = candles[-1].close * (1 + SLIPPAGE_PCT if is_short else 1 - SLIPPAGE_PCT)
        cost = _commission(exit_price * pos["size"])
        gross_pnl = ((pos["entry_price"] - exit_price) * pos["size"] if is_short
                     else (exit_price - pos["entry_price"]) * pos["size"])
        net_pnl = gross_pnl - cost
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
            regime=pos["regime"],
        ))

    return _build_result(config, risk_pct, initial_capital, completed_trades, equity_curve, candles)


# ── Strategy generation ──────────────────────────────────────────────────────

def generate_session_strategies(instrument: str, n: int = 30) -> list[StrategyDefinition]:
    """Generate n session-rotation StrategyDefinition variants.

    Varies morning/midday/afternoon strategy types, triggers, daily loss
    limits, and stop/TP parameters.
    """
    morning_types = ["breakout", "trend_following"]
    midday_types = ["mean_reversion"]
    afternoon_types = ["momentum", "trend_following"]
    daily_limits = [300.0, 500.0, 750.0]
    stop_values = [1.5, 2.0, 2.5]
    tp_values = [1.5, 2.0, 2.5, 3.0]

    strategies: list[StrategyDefinition] = []
    combo_iter = itertools.product(morning_types, midday_types, afternoon_types, daily_limits, stop_values, tp_values)

    for idx, (m_type, mid_type, aft_type, dlimit, sl_val, tp_val) in enumerate(combo_iter):
        if len(strategies) >= n:
            break

        # Pick a trigger/filter combo for each session
        m_combo = SESSION_STRATEGY_MAP[m_type][idx % len(SESSION_STRATEGY_MAP[m_type])]
        mid_combo = SESSION_STRATEGY_MAP[mid_type][idx % len(SESSION_STRATEGY_MAP[mid_type])]
        aft_combo = SESSION_STRATEGY_MAP[aft_type][idx % len(SESSION_STRATEGY_MAP[aft_type])]

        sid = f"SESS-{instrument}-{uuid.uuid4().hex[:8]}"
        name = f"SessionRot {m_type[:3].upper()}/{mid_type[:3].upper()}/{aft_type[:3].upper()} SL{sl_val} TP{tp_val} DL${int(dlimit)}"

        strategies.append(StrategyDefinition(
            strategy_id=sid,
            strategy_name=name,
            strategy_type="hybrid",
            market_type="futures",
            thesis_summary=(
                f"Session rotation: {m_type} in morning, {mid_type} at midday, "
                f"{aft_type} in afternoon. Daily loss limit ${int(dlimit)}."
            ),
            indicators_used=[m_combo["primary"], mid_combo["primary"], aft_combo["primary"]],
            candlestick_patterns_used=[],
            timeframe_stack=["15m"],
            entry_rules={
                "morning": {"trigger": m_combo["trigger"], "filter": m_combo["filter"]},
                "midday": {"trigger": mid_combo["trigger"], "filter": mid_combo["filter"]},
                "afternoon": {"trigger": aft_combo["trigger"], "filter": aft_combo["filter"]},
            },
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": sl_val},
                "take_profit": {"type": "r_multiple", "value": tp_val},
                "time_exit_bars": 48,
            },
            stop_loss_logic={"type": "atr_multiple", "value": sl_val},
            take_profit_logic={"type": "r_multiple", "value": tp_val},
            trailing_stop_or_break_even_logic={},
            session_filters={"allowed_sessions": ["morning", "midday", "afternoon"], "daily_loss_limit": dlimit},
            volatility_filters={"min_atr_percentile": 30, "max_atr_percentile": 90},
            fundamental_filters_if_any={"avoid_fomc": True, "avoid_nfp": True},
            intended_asset_classes=[instrument],
            primary_indicator=m_combo["primary"],
            confirmation_indicator=m_combo["confirmation"],
            entry={"trigger": m_combo["trigger"], "filter": m_combo["filter"]},
            exit={
                "stop_loss": {"type": "atr_multiple", "value": sl_val},
                "take_profit": {"type": "r_multiple", "value": tp_val},
                "time_exit_bars": 48,
            },
            risk={"max_open_positions": 1},
        ))

    return strategies


# ── Internal helpers ─────────────────────────────────────────────────────────

def _session_signal_params(
    config: SessionRotationConfig,
    session: str,
    session_indicators: dict[str, dict],
) -> tuple[str, str, dict]:
    """Return (trigger_name, filter_name, indicators) for the given session."""
    if session == "morning":
        return config.morning_trigger, config.morning_filter, session_indicators["morning"]
    elif session == "midday":
        return config.midday_trigger, config.midday_filter, session_indicators["midday"]
    else:  # afternoon
        return config.afternoon_trigger, config.afternoon_filter, session_indicators["afternoon"]


def _compute_all_session_indicators(
    config: SessionRotationConfig,
    candles: list[Candle],
) -> dict[str, dict]:
    """Pre-compute indicators for each session's strategy config."""
    result = {}
    for session, primary, confirmation in [
        ("morning", config.morning_primary, config.morning_confirmation),
        ("midday", config.midday_primary, config.midday_confirmation),
        ("afternoon", config.afternoon_primary, config.afternoon_confirmation),
    ]:
        tmp = StrategyDefinition(
            strategy_id="_tmp", strategy_name="_tmp", strategy_type="hybrid",
            market_type="futures", thesis_summary="", indicators_used=[],
            candlestick_patterns_used=[], timeframe_stack=["15m"],
            entry_rules={}, exit_rules={}, stop_loss_logic={},
            take_profit_logic={}, trailing_stop_or_break_even_logic={},
            session_filters={}, volatility_filters={},
            fundamental_filters_if_any={}, intended_asset_classes=[],
            primary_indicator=primary,
            confirmation_indicator=confirmation,
        )
        result[session] = compute_indicators(tmp, candles)
    return result


def _tmp_strategy(config: SessionRotationConfig) -> StrategyDefinition:
    """Build a lightweight StrategyDefinition for stop/TP calculation."""
    return StrategyDefinition(
        strategy_id="_tmp", strategy_name="_tmp", strategy_type="hybrid",
        market_type="futures", thesis_summary="", indicators_used=[],
        candlestick_patterns_used=[], timeframe_stack=["15m"],
        entry_rules={}, exit_rules={}, stop_loss_logic={},
        take_profit_logic={}, trailing_stop_or_break_even_logic={},
        session_filters={}, volatility_filters={},
        fundamental_filters_if_any={}, intended_asset_classes=[],
        exit={
            "stop_loss": {"type": config.stop_loss_type, "value": config.stop_loss_value},
            "take_profit": {"type": config.take_profit_type, "value": config.take_profit_value},
            "time_exit_bars": config.time_exit_bars,
        },
    )


def _check_exit(pos, candles, i, config, equity):
    """Check if a position should be exited on this bar."""
    low = candles[i].low
    high = candles[i].high
    close = candles[i].close
    short = pos["direction"] == "short"

    exit_price = None
    exit_reason = None

    if short:
        if high >= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 + SLIPPAGE_PCT), "stop_loss"
        elif low <= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 + SLIPPAGE_PCT), "take_profit"
        elif pos.get("trailing_stop") and high >= pos["trailing_stop"]:
            exit_price, exit_reason = pos["trailing_stop"] * (1 + SLIPPAGE_PCT), "trailing_stop"
        elif config.time_exit_bars and (i - pos["entry_bar"]) >= config.time_exit_bars:
            exit_price, exit_reason = close * (1 + SLIPPAGE_PCT), "time_exit"
    else:
        if low <= pos["stop_price"]:
            exit_price, exit_reason = pos["stop_price"] * (1 - SLIPPAGE_PCT), "stop_loss"
        elif high >= pos["tp_price"]:
            exit_price, exit_reason = pos["tp_price"] * (1 - SLIPPAGE_PCT), "take_profit"
        elif pos.get("trailing_stop") and low <= pos["trailing_stop"]:
            exit_price, exit_reason = pos["trailing_stop"] * (1 - SLIPPAGE_PCT), "trailing_stop"
        elif config.time_exit_bars and (i - pos["entry_bar"]) >= config.time_exit_bars:
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
        size=pos["size"], direction=pos["direction"],
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


def _build_result(
    config: SessionRotationConfig,
    risk_pct: float,
    initial_capital: float,
    trades: list[Trade],
    equity_curve: list[float],
    candles: list[Candle],
) -> BacktestResult:
    """Assemble a BacktestResult from completed trades and equity curve."""
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
    dd_curve = _drawdown_curve(equity_curve)

    # Sharpe & Sortino
    sharpe = _sharpe(equity_curve, candles)
    sortino = _sortino(equity_curve, candles)

    # Compliance
    compliance = check_compliance(dd_pct, "futures")

    strategy_id = f"SESS-ROT-{config.morning_strategy_type[:3]}-{config.midday_strategy_type[:3]}-{config.afternoon_strategy_type[:3]}"

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
        drawdown_curve=dd_curve,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        compliance_status=compliance["status"],
        compliance_reason=compliance["reason"],
        trades=trades,
    )


def _empty_result(config, risk_pct, initial_capital, n):
    """Return a zeroed-out BacktestResult when there's insufficient data."""
    return BacktestResult(
        strategy_id="SESS-ROT-empty",
        risk_pct=risk_pct,
        initial_capital=initial_capital,
        total_return_pct=0.0, net_profit_dollars=0.0,
        gross_profit=0.0, gross_loss=0.0,
        profit_factor=0.0, win_rate=0.0, avg_r_multiple=0.0,
        total_trades=0,
        max_drawdown_pct=0.0, max_drawdown_dollars=0.0,
        best_trade=0.0, worst_trade=0.0,
        long_side_performance={"total_trades": 0, "win_rate": 0, "gross_profit": 0, "gross_loss": 0, "net_pnl": 0, "avg_r_multiple": 0},
        short_side_performance={"total_trades": 0, "win_rate": 0, "gross_profit": 0, "gross_loss": 0, "net_pnl": 0, "avg_r_multiple": 0},
        monthly_returns=[], equity_curve=[initial_capital] * max(n, 1),
        drawdown_curve=[0.0] * max(n, 1),
        sharpe_ratio=0.0, sortino_ratio=0.0,
        compliance_status="compliant", compliance_reason="",
        trades=[],
    )


# ── Metric helpers (mirrors backtester.py) ───────────────────────────────────

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
