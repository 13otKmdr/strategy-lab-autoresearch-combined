"""
Intelligence-first strategy generation factory.

v2: Generates 150 regime-tuned strategies PER ASSET (not 50 blind ones).
Uses scout data to:
  - Weight strategy types toward what works in the current regime
  - Bias direction (long/short) from sentiment
  - De-prioritize strategy families that historically lose on this asset
  - Expand indicator pools for maximum diversity

Each asset gets its own tailored strategy set.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from app.engine.scout import AssetRegime
from app.engine.orb import generate_orb_strategies
from app.engine.vwap_reversion import generate_vwap_strategies
from app.engine.session_rotation import generate_session_strategies
from app.models.strategy import StrategyBatch, StrategyDefinition

# ── Regime-based type weights ────────────────────────────────────────────────

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "trending_up":   {"trend_following": 0.40, "momentum": 0.30, "breakout": 0.15, "mean_reversion": 0.05, "hybrid": 0.10},
    "trending_down": {"trend_following": 0.40, "momentum": 0.30, "breakout": 0.15, "mean_reversion": 0.05, "hybrid": 0.10},
    "ranging":       {"mean_reversion": 0.40, "breakout": 0.20, "hybrid": 0.15, "trend_following": 0.10, "momentum": 0.15},
    "volatile":      {"breakout": 0.35, "momentum": 0.25, "mean_reversion": 0.20, "trend_following": 0.10, "hybrid": 0.10},
}

# Direction weights based on regime + sentiment
DIRECTION_WEIGHTS: dict[str, dict[str, list]] = {
    # (regime, bias) -> [long_weight, short_weight, both_weight]
    "trending_up_bullish":   [0.75, 0.10, 0.15],
    "trending_up_neutral":   [0.60, 0.20, 0.20],
    "trending_up_bearish":   [0.40, 0.35, 0.25],
    "trending_down_bullish": [0.35, 0.40, 0.25],
    "trending_down_neutral": [0.20, 0.60, 0.20],
    "trending_down_bearish": [0.10, 0.75, 0.15],
    "ranging_bullish":       [0.45, 0.35, 0.20],
    "ranging_neutral":       [0.35, 0.35, 0.30],
    "ranging_bearish":       [0.35, 0.45, 0.20],
    "volatile_bullish":      [0.45, 0.30, 0.25],
    "volatile_neutral":      [0.35, 0.35, 0.30],
    "volatile_bearish":      [0.30, 0.45, 0.25],
}

BATCH_TYPES = ["trend_following", "mean_reversion", "breakout", "momentum", "hybrid"]

# ── Expanded indicator pools (20+ per type for more diversity) ───────────────

_INDICATORS: dict[str, list[dict]] = {
    "trend_following": [
        {"type": "EMA", "params": {"period": 9}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 13}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 20}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 34}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 50}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "MACD", "params": {"fast": 8, "slow": 21, "signal": 5}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "MACD", "params": {"fast": 5, "slow": 13, "signal": 4}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "ADX", "params": {"period": 14}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "ADX", "params": {"period": 10}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "ICHIMOKU", "params": {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}, "trigger": "PRICE_ABOVE_CLOUD", "short_trigger": "PRICE_BELOW_CLOUD"},
        {"type": "ICHIMOKU", "params": {"tenkan_period": 7, "kijun_period": 22, "senkou_b_period": 44}, "trigger": "PRICE_ABOVE_CLOUD", "short_trigger": "PRICE_BELOW_CLOUD"},
        {"type": "VWAP", "params": {}, "trigger": "VWAP_CROSS_ABOVE", "short_trigger": "VWAP_CROSS_BELOW"},
        {"type": "DONCHIAN", "params": {"period": 20}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "DONCHIAN", "params": {"period": 40}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "EMA", "params": {"period": 8}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 21}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "MACD", "params": {"fast": 19, "slow": 39, "signal": 9}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "ADX", "params": {"period": 20}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 100}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
    ],
    "mean_reversion": [
        {"type": "RSI", "params": {"period": 5}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 7}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 9}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 14}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 21}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "BB", "params": {"period": 14, "std_dev": 2.0}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "BB", "params": {"period": 20, "std_dev": 2.0}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "BB", "params": {"period": 20, "std_dev": 2.5}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "BB", "params": {"period": 30, "std_dev": 2.0}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "STOCH", "params": {"k_period": 5, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "STOCH", "params": {"k_period": 9, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "STOCH", "params": {"k_period": 14, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "STOCH", "params": {"k_period": 21, "d_period": 5}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "CCI", "params": {"period": 14}, "trigger": "CCI_OVERSOLD", "short_trigger": "CCI_OVERBOUGHT"},
        {"type": "CCI", "params": {"period": 20}, "trigger": "CCI_OVERSOLD", "short_trigger": "CCI_OVERBOUGHT"},
        {"type": "WILLR", "params": {"period": 10}, "trigger": "WILLR_OVERSOLD", "short_trigger": "WILLR_OVERBOUGHT"},
        {"type": "WILLR", "params": {"period": 14}, "trigger": "WILLR_OVERSOLD", "short_trigger": "WILLR_OVERBOUGHT"},
        {"type": "WILLR", "params": {"period": 21}, "trigger": "WILLR_OVERSOLD", "short_trigger": "WILLR_OVERBOUGHT"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}, "trigger": "KC_LOWER_TOUCH", "short_trigger": "KC_UPPER_TOUCH"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 1.5}, "trigger": "KC_LOWER_TOUCH", "short_trigger": "KC_UPPER_TOUCH"},
    ],
    "breakout": [
        {"type": "DONCHIAN", "params": {"period": 10}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "DONCHIAN", "params": {"period": 20}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "DONCHIAN", "params": {"period": 30}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "DONCHIAN", "params": {"period": 55}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "BB", "params": {"period": 10, "std_dev": 1.5}, "trigger": "BB_UPPER_TOUCH", "short_trigger": "BB_LOWER_TOUCH"},
        {"type": "BB", "params": {"period": 20, "std_dev": 2.0}, "trigger": "BB_UPPER_TOUCH", "short_trigger": "BB_LOWER_TOUCH"},
        {"type": "BB", "params": {"period": 20, "std_dev": 2.5}, "trigger": "BB_UPPER_TOUCH", "short_trigger": "BB_LOWER_TOUCH"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 1.5}, "trigger": "KC_UPPER_TOUCH", "short_trigger": "KC_LOWER_TOUCH"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}, "trigger": "KC_UPPER_TOUCH", "short_trigger": "KC_LOWER_TOUCH"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 2.5}, "trigger": "KC_UPPER_TOUCH", "short_trigger": "KC_LOWER_TOUCH"},
        {"type": "ICHIMOKU", "params": {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}, "trigger": "PRICE_ABOVE_CLOUD", "short_trigger": "PRICE_BELOW_CLOUD"},
        {"type": "ICHIMOKU", "params": {"tenkan_period": 5, "kijun_period": 13, "senkou_b_period": 26}, "trigger": "PRICE_ABOVE_CLOUD", "short_trigger": "PRICE_BELOW_CLOUD"},
        {"type": "EMA", "params": {"period": 20}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 50}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "VWAP", "params": {}, "trigger": "VWAP_CROSS_ABOVE", "short_trigger": "VWAP_CROSS_BELOW"},
        {"type": "DONCHIAN", "params": {"period": 15}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "DONCHIAN", "params": {"period": 40}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "BB", "params": {"period": 14, "std_dev": 2.0}, "trigger": "BB_UPPER_TOUCH", "short_trigger": "BB_LOWER_TOUCH"},
        {"type": "KELTNER", "params": {"ema_period": 10, "atr_period": 7, "multiplier": 1.5}, "trigger": "KC_UPPER_TOUCH", "short_trigger": "KC_LOWER_TOUCH"},
        {"type": "EMA", "params": {"period": 10}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
    ],
    "momentum": [
        {"type": "ROC", "params": {"period": 5}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "ROC", "params": {"period": 6}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "ROC", "params": {"period": 10}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "ROC", "params": {"period": 12}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "ROC", "params": {"period": 20}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "MACD", "params": {"fast": 5, "slow": 13, "signal": 4}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "MACD", "params": {"fast": 8, "slow": 17, "signal": 9}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "RSI", "params": {"period": 14}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 9}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "ADX", "params": {"period": 14}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "STOCH", "params": {"k_period": 14, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "STOCH", "params": {"k_period": 5, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "CCI", "params": {"period": 14}, "trigger": "CCI_OVERSOLD", "short_trigger": "CCI_OVERBOUGHT"},
        {"type": "CCI", "params": {"period": 10}, "trigger": "CCI_OVERSOLD", "short_trigger": "CCI_OVERBOUGHT"},
        {"type": "EMA", "params": {"period": 8}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 13}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "ROC", "params": {"period": 14}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "ROC", "params": {"period": 25}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "WILLR", "params": {"period": 14}, "trigger": "WILLR_OVERSOLD", "short_trigger": "WILLR_OVERBOUGHT"},
    ],
    "hybrid": [
        {"type": "RSI", "params": {"period": 14}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "RSI", "params": {"period": 7}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "BB", "params": {"period": 20, "std_dev": 2.0}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "BB", "params": {"period": 14, "std_dev": 2.0}, "trigger": "BB_LOWER_TOUCH", "short_trigger": "BB_UPPER_TOUCH"},
        {"type": "EMA", "params": {"period": 21}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "EMA", "params": {"period": 50}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "DONCHIAN", "params": {"period": 20}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
        {"type": "STOCH", "params": {"k_period": 14, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "STOCH", "params": {"k_period": 9, "d_period": 3}, "trigger": "STOCH_OVERSOLD", "short_trigger": "STOCH_OVERBOUGHT"},
        {"type": "VWAP", "params": {}, "trigger": "VWAP_CROSS_ABOVE", "short_trigger": "VWAP_CROSS_BELOW"},
        {"type": "ICHIMOKU", "params": {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}, "trigger": "PRICE_ABOVE_CLOUD", "short_trigger": "PRICE_BELOW_CLOUD"},
        {"type": "ROC", "params": {"period": 10}, "trigger": "ROC_CROSS_ABOVE", "short_trigger": "ROC_CROSS_BELOW"},
        {"type": "KELTNER", "params": {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}, "trigger": "KC_LOWER_TOUCH", "short_trigger": "KC_UPPER_TOUCH"},
        {"type": "CCI", "params": {"period": 20}, "trigger": "CCI_OVERSOLD", "short_trigger": "CCI_OVERBOUGHT"},
        {"type": "WILLR", "params": {"period": 14}, "trigger": "WILLR_OVERSOLD", "short_trigger": "WILLR_OVERBOUGHT"},
        {"type": "ADX", "params": {"period": 14}, "trigger": "PRICE_ABOVE_EMA", "short_trigger": "PRICE_BELOW_EMA"},
        {"type": "MACD", "params": {"fast": 8, "slow": 21, "signal": 5}, "trigger": "MACD_CROSS_ABOVE", "short_trigger": "MACD_CROSS_BELOW"},
        {"type": "RSI", "params": {"period": 21}, "trigger": "RSI_OVERSOLD", "short_trigger": "RSI_OVERBOUGHT"},
        {"type": "DONCHIAN", "params": {"period": 10}, "trigger": "DC_UPPER_BREAK", "short_trigger": "DC_LOWER_BREAK"},
    ],
}

CONFIRMATIONS = [
    {"type": "EMA", "params": {"period": 20}, "filter": "PRICE_ABOVE_EMA"},
    {"type": "EMA", "params": {"period": 50}, "filter": "PRICE_ABOVE_EMA"},
    {"type": "EMA", "params": {"period": 100}, "filter": "PRICE_ABOVE_EMA"},
    {"type": "EMA", "params": {"period": 200}, "filter": "PRICE_ABOVE_EMA"},
    {"type": "VOLUME", "params": {"period": 20}, "filter": "VOLUME_ABOVE_SMA"},
    {"type": "ATR", "params": {"period": 14}, "filter": "ATR_EXPANDING"},
    {"type": "ADX", "params": {"period": 14}, "filter": "ADX_TRENDING"},
    {"type": "OBV", "params": {}, "filter": "OBV_RISING"},
    {"type": "EMA", "params": {"period": 50}, "filter": "NONE"},
]

STOP_MODELS = [
    {"type": "atr_multiple", "value": 1.0},
    {"type": "atr_multiple", "value": 1.5},
    {"type": "atr_multiple", "value": 2.0},
    {"type": "atr_multiple", "value": 2.5},
    {"type": "atr_multiple", "value": 3.0},
    {"type": "fixed_pct", "value": 0.3},
    {"type": "fixed_pct", "value": 0.5},
    {"type": "fixed_pct", "value": 1.0},
]

TP_MODELS = [
    {"type": "r_multiple", "value": 1.5},
    {"type": "r_multiple", "value": 2.0},
    {"type": "r_multiple", "value": 2.5},
    {"type": "r_multiple", "value": 3.0},
    {"type": "r_multiple", "value": 4.0},
]

TRAILING_MODELS = [
    {"type": "none"},
    {"type": "trailing_atr", "value": 1.5},
    {"type": "trailing_atr", "value": 2.0},
    {"type": "trailing_atr", "value": 2.5},
    {"type": "break_even", "trigger_r": 1.0},
    {"type": "break_even", "trigger_r": 1.5},
]

SESSION_FILTERS = [
    {"allowed_sessions": ["us_regular"], "description": "US Regular Hours (9:30-16:00 ET)"},
    {"allowed_sessions": ["us_extended"], "description": "US Extended Hours"},
    {"allowed_sessions": ["london_overlap"], "description": "London/NY Overlap (8:00-12:00 ET)"},
    {"allowed_sessions": ["all"], "description": "All Sessions"},
]

VOLATILITY_FILTERS = [
    {"min_atr_percentile": 0, "max_atr_percentile": 100, "description": "No filter"},
    {"min_atr_percentile": 25, "max_atr_percentile": 90, "description": "Moderate volatility"},
    {"min_atr_percentile": 40, "max_atr_percentile": 100, "description": "High volatility only"},
]

CANDLESTICK_PATTERNS = [
    [], ["engulfing"], ["doji"], ["hammer", "shooting_star"],
    ["engulfing", "pin_bar"], ["morning_star", "evening_star"],
]

_THESIS_TEMPLATES: dict[str, list[str]] = {
    "trend_following": [
        "Captures sustained directional moves using {indicator}. Enters on {trigger} with {confirmation} confirmation. {stop} stop, {tp} target.",
        "Trend-following system riding {indicator} momentum shifts. Pullback entries confirmed by {confirmation}. ATR-based sizing.",
    ],
    "mean_reversion": [
        "Fades overextended price when {indicator} signals extremes. {confirmation} confirms reversal potential. Tight {stop} stops, {tp} targets.",
        "Statistical mean reversion using {indicator}. Enters at extreme readings, targets return to mean with {tp} profit targets.",
    ],
    "breakout": [
        "Captures range expansion on {indicator} level breaks. Confirmed by {confirmation}. {stop} risk management, {tp} target.",
        "Volatility breakout trading {indicator} channel breaks with {confirmation} momentum confirmation.",
    ],
    "momentum": [
        "Trades short-term momentum via {indicator}. {confirmation} confirms directional pressure. {tp} reward targets with {stop} protection.",
        "Momentum strategy using {indicator} acceleration signals. Enters on crossovers with {stop} risk control.",
    ],
    "hybrid": [
        "Multi-factor approach: {indicator} + {confirmation} for high-conviction entries. Balances trend and reversion signals.",
        "Adaptive strategy using {indicator} as primary signal with {confirmation} regime filter. Regime-aware positioning.",
    ],
}


# ── Public API ───────────────────────────────────────────────────────────────

def generate_for_asset(
    instrument: str,
    regime: AssetRegime,
    seed: int,
    total_strategies: int = 150,
) -> list[StrategyDefinition]:
    """
    Generate regime-tuned strategies for a single asset.

    Uses scout intelligence to:
    1. Weight strategy types toward what works in the current regime
    2. Bias direction (long/short) from sentiment
    3. De-prioritize families that historically lose on this asset
    """
    rng = random.Random(seed)

    # Allocate: 60% indicator-based, 15% ORB, 15% VWAP, 10% session rotation
    indicator_count = round(total_strategies * 0.60)
    orb_count = round(total_strategies * 0.15)
    vwap_count = round(total_strategies * 0.15)
    session_count = total_strategies - indicator_count - orb_count - vwap_count

    # Get type weights from regime
    weights = REGIME_WEIGHTS.get(regime.regime, REGIME_WEIGHTS["ranging"]).copy()

    # De-prioritize worst family if scouted
    worst = regime.worst_strategy_family
    if worst:
        family_map = {
            "macd": "momentum",
            "ema_cross": "trend_following",
            "supertrend": "trend_following",
            "bollinger": "mean_reversion",
            "rsi": "mean_reversion",
            "donchian": "breakout",
        }
        worst_type = family_map.get(worst, "")
        if worst_type in weights:
            penalty = weights[worst_type] * 0.5  # cut worst family's weight in half
            weights[worst_type] -= penalty
            # Redistribute to best-performing type
            best = regime.best_strategy_family
            best_type = family_map.get(best, "hybrid")
            if best_type in weights:
                weights[best_type] += penalty

    # Normalize weights
    total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    # Calculate indicator-based strategies per type
    type_counts: dict[str, int] = {}
    remaining = indicator_count
    for i, (stype, w) in enumerate(weights.items()):
        if i == len(weights) - 1:
            type_counts[stype] = remaining
        else:
            count = round(indicator_count * w)
            type_counts[stype] = count
            remaining -= count

    # Direction weights
    dir_key = f"{regime.regime}_{regime.direction_bias}"
    dir_weights = DIRECTION_WEIGHTS.get(dir_key, [0.35, 0.35, 0.30])

    strategies: list[StrategyDefinition] = []
    global_idx = 0

    for stype, count in type_counts.items():
        pool = _INDICATORS[stype]

        for i in range(count):
            ind = pool[i % len(pool)]
            conf = rng.choice(CONFIRMATIONS)
            stop = rng.choice(STOP_MODELS)
            tp = rng.choice(TP_MODELS)
            trailing = rng.choice(TRAILING_MODELS)
            session = rng.choice(SESSION_FILTERS)
            volatility = rng.choice(VOLATILITY_FILTERS)
            patterns = rng.choice(CANDLESTICK_PATTERNS)

            # Direction from weighted random
            r = rng.random()
            if r < dir_weights[0]:
                direction = "long"
            elif r < dir_weights[0] + dir_weights[1]:
                direction = "short"
            else:
                direction = "both"

            trigger = ind.get("short_trigger", ind["trigger"]) if direction == "short" else ind["trigger"]

            sid = _make_id(instrument, global_idx, seed)
            name = _make_name(stype, ind["type"], instrument, global_idx)
            thesis = _make_thesis(stype, ind, conf, stop, tp, volatility, rng)

            time_exit = rng.choice([None, 16, 24, 48, 96])

            strategy = StrategyDefinition(
                strategy_id=sid,
                strategy_name=name,
                strategy_type=stype,
                market_type="futures",
                thesis_summary=thesis,
                indicators_used=[
                    {"type": ind["type"], "params": ind["params"]},
                    {"type": conf["type"], "params": conf["params"]},
                ],
                candlestick_patterns_used=patterns,
                timeframe_stack=["15min"],
                entry_rules={
                    "trigger": trigger,
                    "filter": conf["filter"],
                    "direction": direction,
                    "description": f"Enter {direction} on {trigger} with {conf['filter']} confirmation",
                },
                exit_rules={
                    "stop_loss": stop,
                    "take_profit": tp,
                    "trailing_stop_atr": trailing.get("value") if trailing["type"] == "trailing_atr" else None,
                    "time_exit_bars": time_exit,
                },
                stop_loss_logic=stop,
                take_profit_logic=tp,
                trailing_stop_or_break_even_logic=trailing,
                session_filters=session,
                volatility_filters=volatility,
                fundamental_filters_if_any={},
                intended_asset_classes=[instrument],
                primary_indicator={"type": ind["type"], "params": ind["params"]},
                confirmation_indicator={"type": conf["type"], "params": conf["params"]},
                entry={"trigger": trigger, "filter": conf["filter"]},
                exit={
                    "stop_loss": stop,
                    "take_profit": tp,
                    "trailing_stop_atr": trailing.get("value") if trailing["type"] == "trailing_atr" else None,
                    "time_exit_bars": time_exit,
                },
                risk={"max_open_positions": 1},
            )
            strategies.append(strategy)
            global_idx += 1

    # Append structural edge strategies
    strategies.extend(generate_orb_strategies(instrument, n=orb_count))
    strategies.extend(generate_vwap_strategies(instrument, n=vwap_count))
    strategies.extend(generate_session_strategies(instrument, n=session_count))

    return strategies


# Legacy function for backward compat
def generate_cycle(seed: int | None = None) -> list[StrategyBatch]:
    """Legacy: Generate 50 strategies across all instruments (v1 behavior)."""
    from app.engine.scout import AssetRegime
    default_regime = AssetRegime(
        instrument="MES", symbol="SPY", regime="ranging",
        direction_bias="neutral", strength=0.5,
    )
    strategies = generate_for_asset("MES", default_regime, seed or 0, total_strategies=50)
    return [StrategyBatch(batch_id=1, batch_type="mixed", strategies=strategies)]


def _make_id(instrument: str, idx: int, seed: int) -> str:
    raw = f"{seed}-{instrument}-{idx}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _make_name(batch_type: str, indicator_type: str, instrument: str, idx: int) -> str:
    type_labels = {
        "trend_following": "Trend",
        "mean_reversion": "MeanRev",
        "breakout": "Breakout",
        "momentum": "Momentum",
        "hybrid": "Hybrid",
    }
    return f"{type_labels.get(batch_type, 'Strat')}-{indicator_type}-{instrument}-{idx + 1:03d}"


def _make_thesis(
    batch_type: str,
    ind: dict,
    conf: dict,
    stop: dict,
    tp: dict,
    volatility: dict,
    rng: random.Random,
) -> str:
    templates = _THESIS_TEMPLATES.get(batch_type, _THESIS_TEMPLATES["hybrid"])
    template = rng.choice(templates)
    return template.format(
        trigger=ind.get("trigger", "signal"),
        indicator=ind["type"],
        confirmation=conf["type"],
        stop=f"{stop['type']}({stop['value']})",
        tp=f"{tp['type']}({tp['value']})",
        volatility=volatility.get("description", "standard"),
    )
