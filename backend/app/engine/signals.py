"""
Signal evaluation — maps strategy entry/exit configs to indicator checks.

Adapted from agent-network/backtesting/signals.py for futures day trading.
"""
from __future__ import annotations

import math

import numpy as np

from app.engine.indicators import (
    adx, atr, bollinger_bands, cci, donchian_channels, ema, ichimoku,
    keltner_channels, macd, obv, roc, rsi, sma, stochastic, volume_sma,
    vwap, williams_r,
)
from app.models.market import Candle
from app.models.strategy import StrategyDefinition

# ── Direction helpers ────────────────────────────────────────────────────────

_SHORT_TRIGGERS: frozenset[str] = frozenset({
    "RSI_OVERBOUGHT", "PRICE_BELOW_EMA", "MACD_CROSS_BELOW",
    "BB_UPPER_TOUCH", "STOCH_OVERBOUGHT", "CCI_OVERBOUGHT",
    "WILLR_OVERBOUGHT", "ROC_CROSS_BELOW", "DC_LOWER_BREAK",
    "KC_UPPER_TOUCH", "PRICE_BELOW_CLOUD", "VWAP_CROSS_BELOW",
})


def is_short_trigger(trigger_name: str) -> bool:
    return trigger_name.upper() in _SHORT_TRIGGERS


def _safe(val) -> bool:
    return not (val is None or (isinstance(val, float) and math.isnan(val)))


# ── Entry trigger evaluators ─────────────────────────────────────────────────

ENTRY_TRIGGERS: dict[str, callable] = {
    "RSI_OVERSOLD": lambda ind, i: (
        _safe(ind["rsi"][i]) and _safe(ind["rsi"][i - 1])
        and ind["rsi"][i] < 30 and ind["rsi"][i - 1] >= 30
    ),
    "RSI_OVERBOUGHT": lambda ind, i: (
        _safe(ind["rsi"][i]) and _safe(ind["rsi"][i - 1])
        and ind["rsi"][i] > 70 and ind["rsi"][i - 1] <= 70
    ),
    "PRICE_ABOVE_EMA": lambda ind, i: (
        _safe(ind["ema_primary"][i]) and _safe(ind["ema_primary"][i - 1])
        and ind["close"][i - 1] <= ind["ema_primary"][i - 1]
        and ind["close"][i] > ind["ema_primary"][i]
    ),
    "PRICE_BELOW_EMA": lambda ind, i: (
        _safe(ind["ema_primary"][i]) and _safe(ind["ema_primary"][i - 1])
        and ind["close"][i - 1] >= ind["ema_primary"][i - 1]
        and ind["close"][i] < ind["ema_primary"][i]
    ),
    "MACD_CROSS_ABOVE": lambda ind, i: (
        _safe(ind["macd_line"][i]) and _safe(ind["macd_sig"][i])
        and _safe(ind["macd_line"][i - 1]) and _safe(ind["macd_sig"][i - 1])
        and ind["macd_line"][i] > ind["macd_sig"][i]
        and ind["macd_line"][i - 1] <= ind["macd_sig"][i - 1]
    ),
    "MACD_CROSS_BELOW": lambda ind, i: (
        _safe(ind["macd_line"][i]) and _safe(ind["macd_sig"][i])
        and _safe(ind["macd_line"][i - 1]) and _safe(ind["macd_sig"][i - 1])
        and ind["macd_line"][i] < ind["macd_sig"][i]
        and ind["macd_line"][i - 1] >= ind["macd_sig"][i - 1]
    ),
    "BB_LOWER_TOUCH": lambda ind, i: (
        _safe(ind["bb_lower"][i]) and _safe(ind["bb_lower"][i - 1])
        and ind["close"][i] <= ind["bb_lower"][i]
        and ind["close"][i - 1] > ind["bb_lower"][i - 1]
    ),
    "BB_UPPER_TOUCH": lambda ind, i: (
        _safe(ind["bb_upper"][i]) and _safe(ind["bb_upper"][i - 1])
        and ind["close"][i] >= ind["bb_upper"][i]
        and ind["close"][i - 1] < ind["bb_upper"][i - 1]
    ),
    "STOCH_OVERSOLD": lambda ind, i: (
        _safe(ind["stoch_k"][i]) and _safe(ind["stoch_k"][i - 1])
        and ind["stoch_k"][i] < 20 and ind["stoch_k"][i - 1] >= 20
    ),
    "STOCH_OVERBOUGHT": lambda ind, i: (
        _safe(ind["stoch_k"][i]) and _safe(ind["stoch_k"][i - 1])
        and ind["stoch_k"][i] > 80 and ind["stoch_k"][i - 1] <= 80
    ),
    "CCI_OVERSOLD": lambda ind, i: (
        _safe(ind["cci"][i]) and _safe(ind["cci"][i - 1])
        and ind["cci"][i] > -100 and ind["cci"][i - 1] <= -100
    ),
    "CCI_OVERBOUGHT": lambda ind, i: (
        _safe(ind["cci"][i]) and _safe(ind["cci"][i - 1])
        and ind["cci"][i] < 100 and ind["cci"][i - 1] >= 100
    ),
    "WILLR_OVERSOLD": lambda ind, i: (
        _safe(ind["willr"][i]) and _safe(ind["willr"][i - 1])
        and ind["willr"][i] > -80 and ind["willr"][i - 1] <= -80
    ),
    "WILLR_OVERBOUGHT": lambda ind, i: (
        _safe(ind["willr"][i]) and _safe(ind["willr"][i - 1])
        and ind["willr"][i] < -20 and ind["willr"][i - 1] >= -20
    ),
    "ROC_CROSS_ABOVE": lambda ind, i: (
        _safe(ind["roc"][i]) and _safe(ind["roc"][i - 1])
        and ind["roc"][i] > 0 and ind["roc"][i - 1] <= 0
    ),
    "ROC_CROSS_BELOW": lambda ind, i: (
        _safe(ind["roc"][i]) and _safe(ind["roc"][i - 1])
        and ind["roc"][i] < 0 and ind["roc"][i - 1] >= 0
    ),
    "DC_UPPER_BREAK": lambda ind, i: (
        _safe(ind["dc_upper"][i]) and _safe(ind["dc_upper"][i - 1])
        and ind["close"][i] > ind["dc_upper"][i - 1]
    ),
    "DC_LOWER_BREAK": lambda ind, i: (
        _safe(ind["dc_lower"][i]) and _safe(ind["dc_lower"][i - 1])
        and ind["close"][i] < ind["dc_lower"][i - 1]
    ),
    "KC_LOWER_TOUCH": lambda ind, i: (
        _safe(ind["kc_lower"][i]) and _safe(ind["kc_lower"][i - 1])
        and ind["close"][i] <= ind["kc_lower"][i]
        and ind["close"][i - 1] > ind["kc_lower"][i - 1]
    ),
    "KC_UPPER_TOUCH": lambda ind, i: (
        _safe(ind["kc_upper"][i]) and _safe(ind["kc_upper"][i - 1])
        and ind["close"][i] >= ind["kc_upper"][i]
        and ind["close"][i - 1] < ind["kc_upper"][i - 1]
    ),
    "PRICE_ABOVE_CLOUD": lambda ind, i: (
        _safe(ind["cloud_upper"][i]) and _safe(ind["cloud_upper"][i - 1])
        and ind["close"][i - 1] <= ind["cloud_upper"][i - 1]
        and ind["close"][i] > ind["cloud_upper"][i]
    ),
    "PRICE_BELOW_CLOUD": lambda ind, i: (
        _safe(ind["cloud_lower"][i]) and _safe(ind["cloud_lower"][i - 1])
        and ind["close"][i - 1] >= ind["cloud_lower"][i - 1]
        and ind["close"][i] < ind["cloud_lower"][i]
    ),
    "VWAP_CROSS_ABOVE": lambda ind, i: (
        _safe(ind["vwap"][i]) and _safe(ind["vwap"][i - 1])
        and ind["close"][i - 1] <= ind["vwap"][i - 1]
        and ind["close"][i] > ind["vwap"][i]
    ),
    "VWAP_CROSS_BELOW": lambda ind, i: (
        _safe(ind["vwap"][i]) and _safe(ind["vwap"][i - 1])
        and ind["close"][i - 1] >= ind["vwap"][i - 1]
        and ind["close"][i] < ind["vwap"][i]
    ),
}

# ── Confirmation evaluators ───────────────────────────────────────────────────

CONFIRMATIONS: dict[str, callable] = {
    "PRICE_ABOVE_EMA": lambda ind, i: (
        _safe(ind["ema_confirmation"][i])
        and ind["close"][i] > ind["ema_confirmation"][i]
    ),
    "PRICE_BELOW_EMA": lambda ind, i: (
        _safe(ind["ema_confirmation"][i])
        and ind["close"][i] < ind["ema_confirmation"][i]
    ),
    "VOLUME_ABOVE_SMA": lambda ind, i: (
        _safe(ind["volume_sma"][i])
        and ind["volume"][i] > ind["volume_sma"][i]
    ),
    "ATR_EXPANDING": lambda ind, i: (
        _safe(ind["atr"][i]) and _safe(ind["atr"][i - 1])
        and ind["atr"][i] > ind["atr"][i - 1]
    ),
    "ADX_TRENDING": lambda ind, i: (
        _safe(ind["adx"][i]) and ind["adx"][i] > 25
    ),
    "OBV_RISING": lambda ind, i: (
        _safe(ind["obv"][i]) and _safe(ind["obv"][i - 1])
        and ind["obv"][i] > ind["obv"][i - 1]
    ),
    "NONE": lambda ind, i: True,
}


# ── Indicator pre-computation ─────────────────────────────────────────────────

def compute_indicators(strategy: StrategyDefinition, candles: list[Candle]) -> dict:
    n = len(candles)
    close = np.array([c.close for c in candles])
    high = np.array([c.high for c in candles])
    low = np.array([c.low for c in candles])
    volume = np.array([c.volume for c in candles])

    ind: dict[str, np.ndarray] = {
        "close": close, "high": high, "low": low, "volume": volume,
        "ema200": ema(close, 200),
    }

    # Primary indicator
    p_type = strategy.primary_indicator.get("type", "RSI").upper()
    p_params = strategy.primary_indicator.get("params", {})

    if p_type == "RSI":
        ind["rsi"] = rsi(close, p_params.get("period", 14))
    elif p_type in ("EMA", "SMA"):
        fn = ema if p_type == "EMA" else sma
        ind["ema_primary"] = fn(close, p_params.get("period", 20))
    elif p_type == "MACD":
        ml, sig, hist = macd(close, p_params.get("fast", 12), p_params.get("slow", 26), p_params.get("signal", 9))
        ind["macd_line"] = ml
        ind["macd_sig"] = sig
        ind["macd_hist"] = hist
    elif p_type in ("BOLLINGER", "BB"):
        upper, middle, lower = bollinger_bands(close, p_params.get("period", 20), p_params.get("std_dev", 2.0))
        ind["bb_upper"] = upper
        ind["bb_middle"] = middle
        ind["bb_lower"] = lower
    elif p_type == "STOCH":
        k, d = stochastic(high, low, close, p_params.get("k_period", 14), p_params.get("d_period", 3))
        ind["stoch_k"] = k
        ind["stoch_d"] = d
    elif p_type == "ATR":
        ind["atr"] = atr(high, low, close, p_params.get("period", 14))
    elif p_type == "ADX":
        adx_line, pdi, mdi = adx(high, low, close, p_params.get("period", 14))
        ind["adx"] = adx_line
        ind["adx_pdi"] = pdi
        ind["adx_mdi"] = mdi
    elif p_type == "CCI":
        ind["cci"] = cci(high, low, close, p_params.get("period", 20))
    elif p_type == "WILLR":
        ind["willr"] = williams_r(high, low, close, p_params.get("period", 14))
    elif p_type == "ROC":
        ind["roc"] = roc(close, p_params.get("period", 12))
    elif p_type == "KELTNER":
        upper, middle, lower = keltner_channels(high, low, close, p_params.get("ema_period", 20), p_params.get("atr_period", 10), p_params.get("multiplier", 2.0))
        ind["kc_upper"] = upper
        ind["kc_middle"] = middle
        ind["kc_lower"] = lower
    elif p_type == "DONCHIAN":
        upper, middle, lower = donchian_channels(high, low, p_params.get("period", 20))
        ind["dc_upper"] = upper
        ind["dc_middle"] = middle
        ind["dc_lower"] = lower
    elif p_type == "ICHIMOKU":
        cloud_upper, cloud_lower = ichimoku(high, low, p_params.get("tenkan_period", 9), p_params.get("kijun_period", 26), p_params.get("senkou_b_period", 52))
        ind["cloud_upper"] = cloud_upper
        ind["cloud_lower"] = cloud_lower
    elif p_type == "OBV":
        ind["obv"] = obv(close, volume)
    elif p_type == "VWAP":
        ind["vwap"] = vwap(high, low, close, volume)
    else:
        ind["rsi"] = rsi(close, 14)

    # Confirmation indicator
    c_type = strategy.confirmation_indicator.get("type", "EMA").upper()
    c_params = strategy.confirmation_indicator.get("params", {})

    if c_type in ("EMA", "SMA"):
        fn = ema if c_type == "EMA" else sma
        ind["ema_confirmation"] = fn(close, c_params.get("period", 50))
    elif c_type == "VOLUME":
        ind["volume_sma"] = volume_sma(volume, c_params.get("period", 20))
    elif c_type == "ATR":
        if "atr" not in ind:
            ind["atr"] = atr(high, low, close, c_params.get("period", 14))
    elif c_type == "ADX":
        if "adx" not in ind:
            adx_line, pdi, mdi = adx(high, low, close, c_params.get("period", 14))
            ind["adx"] = adx_line
    elif c_type == "OBV":
        if "obv" not in ind:
            ind["obv"] = obv(close, volume)
    else:
        ind["volume_sma"] = volume_sma(volume, 20)

    # Ensure all keys exist (guards for signal lambdas)
    _defaults = {
        "atr": lambda: atr(high, low, close, 14),
        "volume_sma": lambda: volume_sma(volume, 20),
        "vwap": lambda: vwap(high, low, close, volume),
    }
    for key, factory in _defaults.items():
        if key not in ind:
            ind[key] = factory()

    _nan_keys = [
        "ema_primary", "ema_confirmation", "rsi", "macd_line", "macd_sig",
        "bb_upper", "bb_lower", "stoch_k", "cci", "willr", "roc", "adx",
        "obv", "dc_upper", "dc_lower", "kc_upper", "kc_lower",
        "cloud_upper", "cloud_lower",
    ]
    for key in _nan_keys:
        if key not in ind:
            ind[key] = np.full(n, np.nan)

    return ind


# ── Signal evaluation ────────────────────────────────────────────────────────

def check_entry(strategy: StrategyDefinition, indicators: dict, bar: int) -> bool:
    if bar < 1:
        return False
    trigger_name = strategy.entry.get("trigger", "NONE")
    confirm_name = strategy.entry.get("filter", "NONE")
    trigger_fn = ENTRY_TRIGGERS.get(trigger_name)
    confirm_fn = CONFIRMATIONS.get(confirm_name, CONFIRMATIONS["NONE"])
    if trigger_fn is None:
        return False
    try:
        return trigger_fn(indicators, bar) and confirm_fn(indicators, bar)
    except (IndexError, ZeroDivisionError):
        return False


def calc_stop_price(
    strategy: StrategyDefinition,
    entry_price: float,
    indicators: dict,
    bar: int,
    short: bool = False,
) -> float:
    sl = strategy.exit.get("stop_loss", {})
    sl_type = sl.get("type", "atr_multiple")
    sl_value = float(sl.get("value", 2.0))
    if sl_type == "atr_multiple":
        atr_val = indicators["atr"][bar]
        if math.isnan(atr_val) or atr_val <= 0:
            atr_val = entry_price * 0.02
        return entry_price + sl_value * atr_val if short else entry_price - sl_value * atr_val
    else:
        return entry_price * (1.0 + sl_value / 100.0) if short else entry_price * (1.0 - sl_value / 100.0)


def calc_take_profit_price(
    strategy: StrategyDefinition,
    entry_price: float,
    stop_price: float,
    short: bool = False,
) -> float:
    tp = strategy.exit.get("take_profit", {})
    tp_type = tp.get("type", "r_multiple")
    tp_value = float(tp.get("value", 2.0))
    risk = abs(entry_price - stop_price)
    if tp_type == "r_multiple":
        return entry_price - risk * tp_value if short else entry_price + risk * tp_value
    else:
        return entry_price * (1.0 - tp_value / 100.0) if short else entry_price * (1.0 + tp_value / 100.0)
