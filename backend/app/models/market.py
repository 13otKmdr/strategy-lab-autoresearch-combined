from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candle:
    ts: int        # Unix milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float


# Instrument specifications
# Uses ETF proxies for Twelve Data free tier (same underlying markets as micro futures)
# SPY tracks MES, QQQ tracks MNQ, DIA tracks MYM, GLD tracks MGC, USO tracks MCL
INSTRUMENTS: dict[str, dict] = {
    "MES": {
        "name": "S&P 500 (SPY proxy for MES)",
        "twelvedata_symbol": "SPY",
        "tick_size": 0.01,
        "tick_value": 1.25,
        "market_type": "futures",
        "exchange": "NYSE",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MNQ": {
        "name": "Nasdaq-100 (QQQ proxy for MNQ)",
        "twelvedata_symbol": "QQQ",
        "tick_size": 0.01,
        "tick_value": 0.50,
        "market_type": "futures",
        "exchange": "NASDAQ",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MYM": {
        "name": "Dow Jones (DIA proxy for MYM)",
        "twelvedata_symbol": "DIA",
        "tick_size": 0.01,
        "tick_value": 0.50,
        "market_type": "futures",
        "exchange": "NYSE",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MGC": {
        "name": "Gold (GLD proxy for MGC)",
        "twelvedata_symbol": "GLD",
        "tick_size": 0.01,
        "tick_value": 1.00,
        "market_type": "futures",
        "exchange": "NYSE",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MCL": {
        "name": "Crude Oil (USO proxy for MCL)",
        "twelvedata_symbol": "USO",
        "tick_size": 0.01,
        "tick_value": 1.00,
        "market_type": "futures",
        "exchange": "NYSE",
        "session_start": "09:00",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
}
