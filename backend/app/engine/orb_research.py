"""
ORB Deep Research — 15 documented variations, comprehensive backtest suite.

Sources:
- Toby Crabel: "Day Trading With Short Term Price Patterns and ORB" (1990)
- Mark Fisher: "The Logical Trader" / ACD Method (2002)
- Quantified Strategies backtests (2024-2025)
- TradingView community / prop firm strategies

Each variation shares a common trade management loop but has unique
entry logic and/or filters.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from app.models.market import Candle
from app.engine.indicators import atr, ema, sma, vwap


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _identify_sessions(candles: list[Candle], gap_ms: int = 7_200_000) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx) for each trading session."""
    sessions = []
    start = 0
    for i in range(1, len(candles)):
        if candles[i].ts - candles[i - 1].ts > gap_ms:
            sessions.append((start, i - 1))
            start = i
    sessions.append((start, len(candles) - 1))
    return sessions


def _session_range(candles: list[Candle], start: int, end: int) -> float:
    """High - low for a session span."""
    h = max(candles[j].high for j in range(start, min(end + 1, len(candles))))
    l = min(candles[j].low for j in range(start, min(end + 1, len(candles))))
    return h - l


def _commission(trade_value: float) -> float:
    return max(1.0, abs(trade_value) * 0.0005)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE TRADE ENGINE (shared across all variations)
# ═══════════════════════════════════════════════════════════════════════════════

def _execute_trade(
    candles: list[Candle],
    entry_bar: int,
    entry_price: float,
    direction: str,
    stop: float,
    tp_mode: str,
    tp_value: float,
    time_exit_bars: int,
    atr_arr: np.ndarray,
    risk_usd: float,
    size: float,
    equity: float,
) -> tuple[float, dict]:
    """Execute a single trade from entry to exit. Returns (new_equity, trade_dict)."""
    n = len(candles)
    trailing_stop = stop
    atr_at_entry = atr_arr[entry_bar] if entry_bar < len(atr_arr) and not math.isnan(atr_arr[entry_bar]) else abs(entry_price - stop)
    risk_dist = abs(entry_price - stop)

    # Fixed target
    target = None
    if tp_mode == "r_multiple":
        target = entry_price + risk_dist * tp_value if direction == "long" else entry_price - risk_dist * tp_value
    elif tp_mode == "range_ext":
        target = entry_price + risk_dist * tp_value if direction == "long" else entry_price - risk_dist * tp_value

    exit_bar = None
    exit_price = None
    exit_reason = None

    for k in range(entry_bar + 1, min(entry_bar + time_exit_bars + 1, n)):
        # Update trailing stop
        if tp_mode == "trailing":
            a = atr_arr[k] if k < len(atr_arr) and not math.isnan(atr_arr[k]) else atr_at_entry
            if direction == "long":
                trailing_stop = max(trailing_stop, candles[k].close - a * tp_value)
            else:
                trailing_stop = min(trailing_stop, candles[k].close + a * tp_value)

        active_stop = trailing_stop if tp_mode == "trailing" else stop

        if direction == "long":
            if candles[k].low <= active_stop:
                exit_price = active_stop * 0.999
                exit_reason = "stop"
                exit_bar = k
                break
            if target and candles[k].high >= target:
                exit_price = target * 0.999
                exit_reason = "target"
                exit_bar = k
                break
        else:
            if candles[k].high >= active_stop:
                exit_price = active_stop * 1.001
                exit_reason = "stop"
                exit_bar = k
                break
            if target and candles[k].low <= target:
                exit_price = target * 1.001
                exit_reason = "target"
                exit_bar = k
                break

    if exit_bar is None:
        exit_bar = min(entry_bar + time_exit_bars, n - 1)
        exit_price = candles[exit_bar].close
        exit_reason = "time"

    pnl = (exit_price - entry_price) * size if direction == "long" else (entry_price - exit_price) * size
    pnl -= _commission(entry_price * size) * 2
    new_equity = equity + pnl

    return new_equity, {
        "pnl": pnl,
        "direction": direction,
        "exit_reason": exit_reason,
        "r_multiple": pnl / risk_usd if risk_usd > 0 else 0,
        "entry_bar": entry_bar,
        "exit_bar": exit_bar,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 15 ORB VARIATIONS — Entry/Filter Logic
# ═══════════════════════════════════════════════════════════════════════════════

def _var01_classic(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V1: Classic ORB — close-based breakout confirmation."""
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        if rb_end >= sess_end:
            continue
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > rh:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var02_crabel_stretch(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V2: Crabel Stretch — volatility-adaptive offset from open."""
    entries = []
    daily_stretches = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        sess_open = candles[sess_start].open
        sess_high = max(candles[j].high for j in range(sess_start, min(sess_start + range_bars + 1, sess_end + 1)))
        sess_low = min(candles[j].low for j in range(sess_start, min(sess_start + range_bars + 1, sess_end + 1)))
        stretch_val = min(sess_high - sess_open, sess_open - sess_low)
        daily_stretches.append(max(stretch_val, 0.001))

        if len(daily_stretches) < 10:
            continue
        avg_stretch = sum(daily_stretches[-10:]) / 10

        long_entry = sess_open + avg_stretch
        short_entry = sess_open - avg_stretch
        rh = max(candles[j].high for j in range(sess_start, min(sess_start + range_bars + 1, sess_end + 1)))
        rl = min(candles[j].low for j in range(sess_start, min(sess_start + range_bars + 1, sess_end + 1)))

        for j in range(sess_start + range_bars + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > long_entry:
                entries.append((j, candles[j].close * 1.001, "long", sess_open - avg_stretch, avg_stretch * 2))
                break
            if direction in ("short", "both") and candles[j].close < short_entry:
                entries.append((j, candles[j].close * 0.999, "short", sess_open + avg_stretch, avg_stretch * 2))
                break
    return entries


def _var03_nr7(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V3: NR7 + ORB — only trade after narrowest range of last 7 days."""
    entries = []
    daily_ranges = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        dr = _session_range(candles, sess_start, sess_end)
        daily_ranges.append(dr)
        if len(daily_ranges) < 8:
            continue
        # Check if PREVIOUS day was NR7
        prev_range = daily_ranges[-2]
        last_7 = daily_ranges[-8:-1]
        if prev_range > min(last_7):
            continue
        # NR7 confirmed — take ORB today
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > rh:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var04_nr4id(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V4: NR4/ID — narrowest range of 4 + inside day."""
    entries = []
    daily_highs, daily_lows, daily_ranges = [], [], []
    for si, (sess_start, sess_end) in enumerate(sessions):
        dh = max(candles[j].high for j in range(sess_start, sess_end + 1))
        dl = min(candles[j].low for j in range(sess_start, sess_end + 1))
        daily_highs.append(dh)
        daily_lows.append(dl)
        daily_ranges.append(dh - dl)
        if len(daily_ranges) < 5:
            continue
        prev_range = daily_ranges[-2]
        prev_high = daily_highs[-2]
        prev_low = daily_lows[-2]
        pprev_high = daily_highs[-3]
        pprev_low = daily_lows[-3]
        is_nr4 = prev_range <= min(daily_ranges[-5:-1])
        is_inside = prev_high < pprev_high and prev_low > pprev_low
        if not (is_nr4 and is_inside):
            continue
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > rh:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var05_fisher_acd(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V5: Fisher ACD — ATR-adaptive A-levels above/below OR."""
    entries = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        # 10-day ATR approximation from the atr array
        atr_val = atr_arr[sess_start] if sess_start < len(atr_arr) and not math.isnan(atr_arr[sess_start]) else (rh - rl)
        a_up = rh + atr_val * 0.20
        a_down = rl - atr_val * 0.20
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > a_up:
                entries.append((j, candles[j].close * 1.001, "long", rl, a_up - rl))
                break
            if direction in ("short", "both") and candles[j].close < a_down:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - a_down))
                break
    return entries


def _var06_vwap_confirm(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V6: ORB + VWAP — only enter if on correct side of VWAP."""
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            v = vwap_arr[j] if j < len(vwap_arr) and not math.isnan(vwap_arr[j]) else None
            if v is None:
                continue
            vwap_slope = (vwap_arr[j] - vwap_arr[max(0, j - 5)]) if j >= 5 and not math.isnan(vwap_arr[j - 5]) else 0
            if direction in ("long", "both") and candles[j].close > rh and close[j] > v and vwap_slope > 0:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl and close[j] < v and vwap_slope < 0:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var07_volume_spike(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V7: ORB + Volume — breakout bar volume must be >= 1.5x range average."""
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        range_avg_vol = sum(volume[sess_start:rb_end + 1]) / max(1, rb_end - sess_start + 1)
        for j in range(rb_end + 1, sess_end + 1):
            vol_ok = volume[j] >= range_avg_vol * 1.5
            if direction in ("long", "both") and candles[j].close > rh and vol_ok:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl and vol_ok:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var08_retest(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V8: ORB Retest — wait for pullback to broken level before entering."""
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        breakout_bar = None
        breakout_dir = None
        for j in range(rb_end + 1, sess_end + 1):
            if candles[j].close > rh and direction in ("long", "both"):
                breakout_bar = j
                breakout_dir = "long"
                break
            if candles[j].close < rl and direction in ("short", "both"):
                breakout_bar = j
                breakout_dir = "short"
                break
        if breakout_bar is None:
            continue
        # Wait for retest within 8 bars
        for j in range(breakout_bar + 1, min(breakout_bar + 9, sess_end + 1)):
            if breakout_dir == "long" and candles[j].low <= rh * 1.002:
                entries.append((j, rh * 1.001, "long", rl, rh - rl))
                break
            if breakout_dir == "short" and candles[j].high >= rl * 0.998:
                entries.append((j, rl * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var09_gap_filter(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V9: ORB Gap — only trade in direction of overnight gap."""
    entries = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        if si == 0:
            continue
        prev_close = candles[sessions[si - 1][1]].close
        curr_open = candles[sess_start].open
        gap = curr_open - prev_close
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if gap > 0 and direction in ("long", "both") and candles[j].close > rh:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if gap < 0 and direction in ("short", "both") and candles[j].close < rl:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var10_fade(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V10: ORB Fade — counter-trend on wide ranges."""
    entries = []
    daily_ranges = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        rs = rh - rl
        daily_ranges.append(rs)
        if len(daily_ranges) < 5 or rs <= 0:
            continue
        avg_range = sum(daily_ranges[-6:-1]) / 5
        if rs < avg_range * 1.3:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].low <= rl:
                a = atr_arr[j] if j < len(atr_arr) and not math.isnan(atr_arr[j]) else rs * 0.5
                entries.append((j, rl * 1.001, "long", rl - a, rs))
                break
            if direction in ("short", "both") and candles[j].high >= rh:
                a = atr_arr[j] if j < len(atr_arr) and not math.isnan(atr_arr[j]) else rs * 0.5
                entries.append((j, rh * 0.999, "short", rh + a, rs))
                break
    return entries


def _var11_trend_filter(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V11: ORB + Prior Day Trend — align with yesterday's direction."""
    entries = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        if si == 0:
            continue
        ps, pe = sessions[si - 1]
        prev_open = candles[ps].open
        prev_close = candles[pe].close
        bullish_day = prev_close > prev_open
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if bullish_day and direction in ("long", "both") and candles[j].close > rh:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if not bullish_day and direction in ("short", "both") and candles[j].close < rl:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var12_ema_filter(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V12: ORB + EMA — only breakout in EMA direction."""
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            e = ema20[j] if j < len(ema20) and not math.isnan(ema20[j]) else None
            if e is None:
                continue
            if direction in ("long", "both") and candles[j].close > rh and close[j] > e:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl and close[j] < e:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var13_trailing_runner(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V13: ORB + Trailing — no fixed TP, trail to catch runners."""
    # Same entries as classic, but tp_mode forced to "trailing" in runner
    return _var01_classic(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw)


def _var14_multi_tf(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V14: Multi-TF ORB — breakout must align with higher TF EMA (50-period)."""
    ema50 = ema(close, 50)
    entries = []
    for sess_start, sess_end in sessions:
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            e50 = ema50[j] if j < len(ema50) and not math.isnan(ema50[j]) else None
            if e50 is None:
                continue
            if direction in ("long", "both") and candles[j].close > rh and close[j] > e50:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl and close[j] < e50:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


def _var15_prev_day_hl(candles, sessions, range_bars, direction, atr_arr, close, high, low, volume, ema20, vwap_arr, vol_sma, **kw):
    """V15: ORB + Previous Day H/L — double breakout of OR and prior day level."""
    entries = []
    for si, (sess_start, sess_end) in enumerate(sessions):
        if si == 0:
            continue
        ps, pe = sessions[si - 1]
        prev_high = max(candles[j].high for j in range(ps, pe + 1))
        prev_low = min(candles[j].low for j in range(ps, pe + 1))
        rb_end = min(sess_start + range_bars, sess_end)
        rh = max(candles[j].high for j in range(sess_start, rb_end + 1))
        rl = min(candles[j].low for j in range(sess_start, rb_end + 1))
        if rh <= rl:
            continue
        for j in range(rb_end + 1, sess_end + 1):
            if direction in ("long", "both") and candles[j].close > rh and candles[j].close > prev_high:
                entries.append((j, candles[j].close * 1.001, "long", rl, rh - rl))
                break
            if direction in ("short", "both") and candles[j].close < rl and candles[j].close < prev_low:
                entries.append((j, candles[j].close * 0.999, "short", rh, rh - rl))
                break
    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# VARIATION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

VARIATIONS = {
    "V01_Classic":       (_var01_classic,       "r_multiple"),
    "V02_Crabel_Stretch":(_var02_crabel_stretch, "r_multiple"),
    "V03_NR7":           (_var03_nr7,           "r_multiple"),
    "V04_NR4_ID":        (_var04_nr4id,         "r_multiple"),
    "V05_Fisher_ACD":    (_var05_fisher_acd,    "r_multiple"),
    "V06_VWAP_Confirm":  (_var06_vwap_confirm,  "r_multiple"),
    "V07_Volume_Spike":  (_var07_volume_spike,  "r_multiple"),
    "V08_Retest":        (_var08_retest,        "r_multiple"),
    "V09_Gap_Filter":    (_var09_gap_filter,    "r_multiple"),
    "V10_Fade":          (_var10_fade,          "r_multiple"),
    "V11_Trend_Filter":  (_var11_trend_filter,  "r_multiple"),
    "V12_EMA_Filter":    (_var12_ema_filter,    "r_multiple"),
    "V13_Trailing":      (_var13_trailing_runner, "trailing"),
    "V14_Multi_TF":      (_var14_multi_tf,      "r_multiple"),
    "V15_Prev_Day_HL":   (_var15_prev_day_hl,   "r_multiple"),
}


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER BACKTEST RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_orb_variation_backtest(
    candles: list[Candle],
    variation: str,
    range_bars: int = 2,
    direction: str = "long",
    stop_mode: str = "range",
    tp_value: float = 2.0,
    time_exit_bars: int = 16,
    risk_pct: float = 0.25,
    initial_capital: float = 50000.0,
) -> dict:
    """Run a single ORB variation backtest and return stats."""
    n = len(candles)
    if n < 100:
        return {"variation": variation, "trades": 0}

    close = np.array([c.close for c in candles])
    high_arr = np.array([c.high for c in candles])
    low_arr = np.array([c.low for c in candles])
    volume = np.array([c.volume for c in candles])
    atr_arr = atr(high_arr, low_arr, close, 14)
    ema20 = ema(close, 20)
    vwap_arr = vwap(high_arr, low_arr, close, volume)
    vol_sma = sma(volume, 20)

    sessions = _identify_sessions(candles)
    if len(sessions) < 3:
        return {"variation": variation, "trades": 0}

    var_fn, default_tp_mode = VARIATIONS.get(variation, (None, "r_multiple"))
    if var_fn is None:
        return {"variation": variation, "trades": 0}

    tp_mode = "trailing" if variation == "V13_Trailing" else default_tp_mode

    entries = var_fn(
        candles=candles, sessions=sessions, range_bars=range_bars,
        direction=direction, atr_arr=atr_arr, close=close,
        high=high_arr, low=low_arr, volume=volume, ema20=ema20,
        vwap_arr=vwap_arr, vol_sma=vol_sma,
    )

    if not entries:
        return {"variation": variation, "trades": 0}

    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    trades = []

    for entry_bar, entry_price, entry_dir, stop, range_size in entries:
        risk_usd = equity * (risk_pct / 100.0)
        risk_dist = abs(entry_price - stop)
        if risk_dist <= 0:
            continue
        size = risk_usd / risk_dist

        equity, trade = _execute_trade(
            candles, entry_bar, entry_price, entry_dir, stop,
            tp_mode, tp_value, time_exit_bars, atr_arr, risk_usd, size, equity,
        )
        trades.append(trade)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    if not trades:
        return {"variation": variation, "trades": 0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)

    return {
        "variation": variation,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "pnl": equity - initial_capital,
        "return_pct": (equity - initial_capital) / initial_capital,
        "pf": pf,
        "wr": len(wins) / len(trades),
        "dd": max_dd,
        "avg_r": sum(t["r_multiple"] for t in trades) / len(trades),
        "best": max(t["pnl"] for t in trades),
        "worst": min(t["pnl"] for t in trades),
        "target_exits": sum(1 for t in trades if t["exit_reason"] == "target"),
        "stop_exits": sum(1 for t in trades if t["exit_reason"] == "stop"),
        "time_exits": sum(1 for t in trades if t["exit_reason"] == "time"),
    }


def run_full_research(candles_by_instrument: dict[str, list[Candle]]) -> list[dict]:
    """Run the complete 15-variation × 5-asset research suite."""
    configs = [
        {"range_bars": 2, "direction": "long", "tp_value": 2.0, "time_exit_bars": 16},
        {"range_bars": 2, "direction": "long", "tp_value": 3.0, "time_exit_bars": 24},
        {"range_bars": 2, "direction": "short", "tp_value": 2.0, "time_exit_bars": 16},
        {"range_bars": 3, "direction": "long", "tp_value": 2.0, "time_exit_bars": 16},
        {"range_bars": 3, "direction": "long", "tp_value": 3.0, "time_exit_bars": 24},
        {"range_bars": 4, "direction": "long", "tp_value": 2.0, "time_exit_bars": 24},
    ]

    all_results = []
    for instrument, candles in candles_by_instrument.items():
        for var_name in VARIATIONS:
            for cfg in configs:
                r = run_orb_variation_backtest(
                    candles, var_name, **cfg,
                )
                r["instrument"] = instrument
                r["config"] = f"rb{cfg['range_bars']} {cfg['direction']} {cfg['tp_value']}R te{cfg['time_exit_bars']}"
                all_results.append(r)

    return all_results
