"""
Twelve Data API client for fetching 15-minute OHLCV candle data.

Supports:
- Single fetch (up to 5,000 candles)
- Paginated 2-year fetch (~33,000 candles via multiple calls)
- SQLite candle caching to avoid re-fetching

Free tier: 800 API calls/day, 8 calls/min.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone, timedelta

import httpx

from app.config import DATABASE_PATH, PROP_ALLOW_ETF_PROXY_DATA, PROP_PROFILE, TWELVEDATA_API_KEY
from app.engine.prop_profile import BROAD_RESEARCH_PROFILES
from app.models.market import Candle, INSTRUMENTS

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com"
RATE_LIMIT_DELAY = 8  # seconds between calls (free tier: 8/min)


def _prop_profile_blocks_proxy_data(instrument: str) -> bool:
    """Fail closed when challenge mode would otherwise use ETF proxy prices.

    The DRB/futures sizing engines interpret prices as native futures prices.
    ETF proxies such as DIA/SPY/QQQ are not on the same tick scale, so they are
    blocked by default for prop-profile simulations. The cycle falls back to
    futures-like mock data until a true futures data source is wired in.
    """
    profile = (PROP_PROFILE or "").strip().lower()
    if profile in BROAD_RESEARCH_PROFILES or PROP_ALLOW_ETF_PROXY_DATA:
        return False
    spec = INSTRUMENTS.get(instrument, {})
    proxy_symbol = spec.get("twelvedata_symbol")
    return bool(proxy_symbol and proxy_symbol != instrument)


def _parse_candles(data: dict) -> list[Candle]:
    """Parse Twelve Data JSON response into Candle list."""
    candles = []
    for bar in data.get("values", []):
        try:
            dt = datetime.strptime(bar["datetime"], "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp() * 1000)
            candles.append(Candle(
                ts=ts,
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(bar.get("volume", 0)),
            ))
        except (KeyError, ValueError) as e:
            logger.warning("Skipping malformed bar: %s", e)
    return candles


# ── Candle Cache ─────────────────────────────────────────────────────────────

def _init_cache():
    """Create candle_cache table if needed."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candle_cache (
            instrument TEXT NOT NULL,
            interval TEXT NOT NULL,
            ts INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            PRIMARY KEY (instrument, interval, ts)
        )
    """)
    conn.commit()
    conn.close()


def _save_to_cache(instrument: str, interval: str, candles: list[Candle]):
    """Persist candles to SQLite cache."""
    _init_cache()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.executemany(
        "INSERT OR IGNORE INTO candle_cache (instrument, interval, ts, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(instrument, interval, c.ts, c.open, c.high, c.low, c.close, c.volume) for c in candles],
    )
    conn.commit()
    conn.close()
    logger.info("Cached %d candles for %s/%s", len(candles), instrument, interval)


def _load_from_cache(instrument: str, interval: str) -> list[Candle]:
    """Load candles from SQLite cache."""
    _init_cache()
    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM candle_cache WHERE instrument = ? AND interval = ? ORDER BY ts",
        (instrument, interval),
    ).fetchall()
    conn.close()
    return [Candle(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]


# ── API Fetch Functions ──────────────────────────────────────────────────────

async def fetch_candles(
    instrument: str,
    interval: str = "15min",
    outputsize: int = 5000,
) -> list[Candle]:
    """Fetch up to 5,000 candles from Twelve Data API."""
    spec = INSTRUMENTS.get(instrument)
    if not spec:
        raise ValueError(f"Unknown instrument: {instrument}")

    if _prop_profile_blocks_proxy_data(instrument):
        logger.warning("Blocked ETF proxy data for %s under challenge profile", instrument)
        return []

    symbol = spec["twelvedata_symbol"]

    if not TWELVEDATA_API_KEY:
        logger.warning("No TWELVEDATA_API_KEY set — returning empty candle list")
        return []

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": min(outputsize, 5000),
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/time_series", params=params)
        resp.raise_for_status()
        data = resp.json()

    if "values" not in data:
        error_msg = data.get("message", "Unknown error")
        logger.error("Twelve Data API error for %s: %s", symbol, error_msg)
        return []

    candles = _parse_candles(data)
    candles.sort(key=lambda c: c.ts)
    logger.info("Fetched %d candles for %s (%s)", len(candles), instrument, symbol)
    return candles


async def fetch_candles_range(
    instrument: str,
    start_date: str,
    end_date: str,
    interval: str = "15min",
) -> list[Candle]:
    """Fetch candles for a specific date range."""
    spec = INSTRUMENTS.get(instrument)
    if not spec:
        raise ValueError(f"Unknown instrument: {instrument}")

    if _prop_profile_blocks_proxy_data(instrument):
        logger.warning("Blocked ETF proxy data for %s under challenge profile", instrument)
        return []

    symbol = spec["twelvedata_symbol"]

    if not TWELVEDATA_API_KEY:
        return []

    params = {
        "symbol": symbol,
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "outputsize": 5000,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/time_series", params=params)
        resp.raise_for_status()
        data = resp.json()

    if "values" not in data:
        error_msg = data.get("message", "Unknown error")
        logger.error("Twelve Data range fetch error for %s: %s", symbol, error_msg)
        return []

    candles = _parse_candles(data)
    candles.sort(key=lambda c: c.ts)
    return candles


async def fetch_2y_candles(
    instrument: str,
    interval: str = "15min",
    use_cache: bool = True,
) -> list[Candle]:
    """
    Fetch 2 years of candles with pagination and caching.

    Makes multiple API calls (max 5000 candles each) to tile the 2-year window.
    Caches results in SQLite so subsequent calls are instant.

    Returns ~33,000 candles for 15min interval.
    """
    # Check cache first
    if use_cache:
        cached = _load_from_cache(instrument, interval)
        if len(cached) > 20000:  # good enough — have substantial data
            logger.info("Using cached data for %s: %d candles", instrument, len(cached))
            return cached

    if not TWELVEDATA_API_KEY:
        logger.warning("No API key — cannot fetch 2y data for %s", instrument)
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=730)  # ~2 years

    # Paginate in ~4-month chunks (each ~5000 candles at 15min)
    all_candles: list[Candle] = []
    chunk_days = 120  # ~4 months per chunk
    current_start = start
    chunk_num = 0

    while current_start < now:
        chunk_end = min(current_start + timedelta(days=chunk_days), now)
        start_str = current_start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")

        chunk_num += 1
        logger.info("Fetching %s chunk %d: %s to %s", instrument, chunk_num, start_str[:10], end_str[:10])

        try:
            chunk_candles = await fetch_candles_range(instrument, start_str, end_str, interval)
            all_candles.extend(chunk_candles)
            logger.info("  Got %d candles (total: %d)", len(chunk_candles), len(all_candles))
        except Exception as e:
            logger.warning("  Chunk fetch failed: %s", e)

        current_start = chunk_end
        if current_start < now:
            time.sleep(RATE_LIMIT_DELAY)  # rate limit between calls

    # Deduplicate by timestamp and sort
    seen = set()
    unique: list[Candle] = []
    for c in all_candles:
        if c.ts not in seen:
            seen.add(c.ts)
            unique.append(c)
    unique.sort(key=lambda c: c.ts)

    logger.info("Total unique candles for %s: %d", instrument, len(unique))

    # Save to cache
    if unique:
        _save_to_cache(instrument, interval, unique)

    return unique
