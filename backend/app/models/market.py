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
#
# Dual-mode data sources:
#   1. ETF proxy mode (default for Twelve Data free tier):
#      SPY tracks MES, QQQ tracks MNQ, DIA tracks MYM, GLD tracks MGC, USO tracks MCL
#      These are BLOCKED under challenge profiles (prop_profile + twelvedata guard).
#
#   2. Futures-native mode (ProjectX API):
#      Uses real contract IDs like "CON.F.US.MYM.M26"
#      Provides actual futures prices on the correct tick scale.
#      Preferred for any challenge/backtesting work.
#
INSTRUMENTS: dict[str, dict] = {
    "MES": {
        "name": "Micro E-mini S&P 500",
        "twelvedata_symbol": "SPY",  # ETF proxy — blocked under challenge profile
        "projectx_contract_id": "CON.F.US.MES",  # real futures (front-month suffix added at runtime)
        "tick_size": 0.25,
        "tick_value": 1.25,
        "market_type": "futures",
        "exchange": "CME",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MNQ": {
        "name": "Micro E-mini Nasdaq-100",
        "twelvedata_symbol": "QQQ",  # ETF proxy — blocked under challenge profile
        "projectx_contract_id": "CON.F.US.MNQ",
        "tick_size": 0.25,
        "tick_value": 0.50,
        "market_type": "futures",
        "exchange": "CME",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MYM": {
        "name": "Micro E-mini Dow",
        "twelvedata_symbol": "DIA",  # ETF proxy — blocked under challenge profile
        "projectx_contract_id": "CON.F.US.MYM",
        "tick_size": 1,
        "tick_value": 0.50,
        "market_type": "futures",
        "exchange": "CBOT",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MGC": {
        "name": "Micro Gold",
        "twelvedata_symbol": "GLD",  # ETF proxy — blocked under challenge profile
        "projectx_contract_id": "CON.F.US.MGC",
        "tick_size": 0.10,
        "tick_value": 1.00,
        "market_type": "futures",
        "exchange": "COMEX",
        "session_start": "09:30",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
    "MCL": {
        "name": "Micro Crude Oil",
        "twelvedata_symbol": "USO",  # ETF proxy — blocked under challenge profile
        "projectx_contract_id": "CON.F.US.MCL",
        "tick_size": 0.01,
        "tick_value": 1.00,
        "market_type": "futures",
        "exchange": "NYMEX",
        "session_start": "09:00",
        "session_end": "16:00",
        "timezone": "America/New_York",
    },
}


def get_projectx_contract_id(symbol: str, month_year: str = "") -> str:
    """Build a full ProjectX contract ID from base symbol + month code.

    Args:
        symbol: e.g. "MYM", "MES"
        month_year: e.g. "M26" for June 2026, "U25" for Sep 2025

    Returns:
        Full contract ID like "CON.F.US.MYM.M26"

    Example:
        >>> get_projectx_contract_id("MYM", "M26")
        'CON.F.US.MYM.M26'
    """
    spec = INSTRUMENTS.get(symbol)
    if spec is None:
        raise ValueError(f"Unknown instrument symbol: {symbol}")
    base = spec["projectx_contract_id"]
    if month_year:
        return f"{base}.{month_year}"
    return base
