"""
Realistic mock OHLCV data generator for offline development and testing.

Generates synthetic price series that mimic real futures behavior:
- Geometric Brownian Motion base
- Intraday volatility patterns (higher at open/close)
- Mean-reverting tendencies
- Volume patterns that correlate with price movement
"""
from __future__ import annotations

import math
import random

import numpy as np

from app.models.market import Candle


# Approximate base prices and daily volatility for each instrument
_INSTRUMENT_PROFILES: dict[str, dict] = {
    "MES": {"base_price": 5200.0, "daily_vol": 0.012, "tick": 0.25},
    "MNQ": {"base_price": 18500.0, "daily_vol": 0.015, "tick": 0.25},
    "MYM": {"base_price": 39500.0, "daily_vol": 0.010, "tick": 1.0},
    "MGC": {"base_price": 2350.0, "daily_vol": 0.011, "tick": 0.10},
    "MCL": {"base_price": 78.0, "daily_vol": 0.018, "tick": 0.01},
}


def generate_mock_candles(
    instrument: str = "MES",
    num_candles: int = 5000,
    interval_minutes: int = 15,
    seed: int = 42,
) -> list[Candle]:
    """
    Generate realistic mock 15-minute candles for a given instrument.

    Args:
        instrument: Instrument code (MES, MNQ, MYM, MGC, MCL)
        num_candles: Number of candles to generate
        interval_minutes: Candle interval in minutes
        seed: Random seed for reproducibility

    Returns:
        List of Candle objects sorted chronologically
    """
    rng = np.random.default_rng(seed)
    profile = _INSTRUMENT_PROFILES.get(instrument, _INSTRUMENT_PROFILES["MES"])

    base_price = profile["base_price"]
    daily_vol = profile["daily_vol"]
    tick = profile["tick"]

    # Scale daily vol to per-bar vol (assuming ~26 bars per day for 15m)
    bars_per_day = int(6.5 * 60 / interval_minutes)  # 6.5 trading hours
    bar_vol = daily_vol / math.sqrt(bars_per_day)

    # Generate price series using GBM with mean reversion
    prices = np.zeros(num_candles)
    prices[0] = base_price
    mean_price = base_price

    for i in range(1, num_candles):
        # Slight mean reversion (pulls price back toward base over time)
        reversion = 0.001 * (mean_price - prices[i - 1]) / mean_price

        # Random walk with drift
        shock = rng.normal(reversion, bar_vol)
        prices[i] = prices[i - 1] * (1 + shock)

        # Slowly drift the mean
        mean_price = mean_price * 0.9999 + prices[i] * 0.0001

    # Generate OHLCV candles
    candles: list[Candle] = []
    # Start from a realistic timestamp (Jan 2 2025, 9:30 AM ET)
    base_ts = 1735826400000  # 2025-01-02 14:30:00 UTC
    interval_ms = interval_minutes * 60 * 1000

    for i in range(num_candles):
        ts = base_ts + i * interval_ms
        close = prices[i]

        # Intraday bar position (0-25 for 26 bars/day)
        bar_of_day = i % bars_per_day

        # Volatility multiplier (higher at open and close)
        if bar_of_day < 2 or bar_of_day > bars_per_day - 3:
            vol_mult = 1.8
        elif bar_of_day < 6:
            vol_mult = 1.3
        else:
            vol_mult = 1.0

        # Generate high/low spread
        spread = abs(rng.normal(0, bar_vol * vol_mult)) * close
        high = close + spread * rng.uniform(0.3, 1.0)
        low = close - spread * rng.uniform(0.3, 1.0)

        # Open is previous close with small gap
        if i > 0:
            gap = rng.normal(0, bar_vol * 0.3) * prices[i - 1]
            open_price = prices[i - 1] + gap
        else:
            open_price = close * (1 + rng.normal(0, bar_vol * 0.5))

        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        # Snap to tick size
        open_price = round(open_price / tick) * tick
        high = round(high / tick) * tick
        low = round(low / tick) * tick
        close = round(close / tick) * tick

        # Volume: higher at open/close, correlated with price movement
        base_vol = 500 + rng.poisson(300)
        vol_adj = vol_mult * (1 + abs(close - open_price) / close * 50)
        volume = max(10, int(base_vol * vol_adj))

        candles.append(Candle(
            ts=ts,
            open=open_price,
            high=max(high, low + tick),  # ensure high > low
            low=low,
            close=close,
            volume=float(volume),
        ))

    return candles
