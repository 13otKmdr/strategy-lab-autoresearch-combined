"""ProjectX / TopstepX market data provider.

Fetches real futures OHLCV bars via the ProjectX History API.
This replaces the ETF proxy data from Twelve Data with actual futures prices.

Usage:
  provider = ProjectXMarketDataProvider(client)
  candles = await provider.fetch_candles("CON.F.US.MYM.M26", ...)

The candles are returned in the same Candle format used everywhere else,
so this is a drop-in replacement for twelvedata.fetch_candles().
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, timedelta

from app.config import DATABASE_PATH
from app.models.market import Candle
from app.execution.projectx_client import ProjectXClient, TimeframeUnit

logger = logging.getLogger(__name__)

# ── SQLite Cache ─────────────────────────────────────────────────────────────

def _init_cache():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS futures_candle_cache (
            contract_id TEXT NOT NULL,
            interval TEXT NOT NULL,
            ts INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            PRIMARY KEY (contract_id, interval, ts)
        )
    """)
    conn.commit()
    conn.close()


def _save_to_cache(contract_id: str, interval: str, candles: list[Candle]):
    _init_cache()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.executemany(
        "INSERT OR IGNORE INTO futures_candle_cache "
        "(contract_id, interval, ts, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(contract_id, interval, c.ts, c.open, c.high, c.low, c.close, c.volume) for c in candles],
    )
    conn.commit()
    conn.close()
    logger.info("Cached %d futures candles for %s/%s", len(candles), contract_id, interval)


def _load_from_cache(contract_id: str, interval: str) -> list[Candle]:
    _init_cache()
    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume "
        "FROM futures_candle_cache WHERE contract_id = ? AND interval = ? ORDER BY ts",
        (contract_id, interval),
    ).fetchall()
    conn.close()
    return [Candle(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]


# ── Timeframe Mapping ────────────────────────────────────────────────────────

# Map our interval strings to ProjectX unit + unitNumber
INTERVAL_MAP: dict[str, tuple[TimeframeUnit, int]] = {
    "1min": (TimeframeUnit.MINUTE, 1),
    "5min": (TimeframeUnit.MINUTE, 5),
    "15min": (TimeframeUnit.MINUTE, 15),
    "30min": (TimeframeUnit.MINUTE, 30),
    "1h": (TimeframeUnit.HOUR, 1),
    "4h": (TimeframeUnit.HOUR, 4),
    "1d": (TimeframeUnit.DAY, 1),
}


def _parse_bar_timestamp(ts_str: str) -> int:
    """Parse ProjectX bar timestamp to Unix milliseconds."""
    # ProjectX returns ISO format like "2024-12-20T14:00:00+00:00"
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# ── Provider ─────────────────────────────────────────────────────────────────

class ProjectXMarketDataProvider:
    """Fetches real futures bars from ProjectX History API.

    Drop-in replacement for twelvedata.fetch_candles() that returns
    actual futures contract prices instead of ETF proxies.
    """

    def __init__(self, client: ProjectXClient) -> None:
        self._client = client

    async def fetch_candles(
        self,
        contract_id: str,
        interval: str = "15min",
        outputsize: int = 5000,
        use_cache: bool = True,
    ) -> list[Candle]:
        """Fetch recent candles for a futures contract.

        Args:
            contract_id: e.g. "CON.F.US.MYM.M26"
            interval: bar interval ("1min", "5min", "15min", "1h", "1d")
            outputsize: max bars to return (up to 20,000 from API)
            use_cache: check SQLite cache first
        """
        if use_cache:
            cached = _load_from_cache(contract_id, interval)
            if len(cached) > outputsize * 0.8:
                logger.info("Using cached futures data for %s: %d candles", contract_id, len(cached))
                return cached[-outputsize:]

        unit, unit_number = INTERVAL_MAP.get(interval, (TimeframeUnit.MINUTE, 15))

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=730)  # 2 years

        bars = await self._client.retrieve_bars(
            contract_id=contract_id,
            start_time=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_time=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            unit=unit,
            unit_number=unit_number,
            limit=min(outputsize, 20000),
        )

        candles = [
            Candle(
                ts=_parse_bar_timestamp(b.timestamp),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in bars
        ]
        candles.sort(key=lambda c: c.ts)

        if candles:
            _save_to_cache(contract_id, interval, candles)

        logger.info("Fetched %d futures candles for %s (%s)", len(candles), contract_id, interval)
        return candles

    async def fetch_candles_range(
        self,
        contract_id: str,
        start_date: str,
        end_date: str,
        interval: str = "15min",
    ) -> list[Candle]:
        """Fetch candles for a specific date range.

        Args:
            start_date: ISO format date/datetime string
            end_date: ISO format date/datetime string
        """
        unit, unit_number = INTERVAL_MAP.get(interval, (TimeframeUnit.MINUTE, 15))

        # Normalize to full ISO datetime if just a date
        if len(start_date) == 10:
            start_date += "T00:00:00Z"
        if len(end_date) == 10:
            end_date += "T23:59:59Z"

        bars = await self._client.retrieve_bars(
            contract_id=contract_id,
            start_time=start_date,
            end_time=end_date,
            unit=unit,
            unit_number=unit_number,
            limit=20000,
        )

        candles = [
            Candle(
                ts=_parse_bar_timestamp(b.timestamp),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in bars
        ]
        candles.sort(key=lambda c: c.ts)
        return candles

    async def fetch_2y_candles(
        self,
        contract_id: str,
        interval: str = "15min",
        use_cache: bool = True,
    ) -> list[Candle]:
        """Fetch ~2 years of futures bars with caching.

        Paginates in 4-month chunks to stay within API limits.
        """
        if use_cache:
            cached = _load_from_cache(contract_id, interval)
            if len(cached) > 20000:
                logger.info("Using cached 2y data for %s: %d candles", contract_id, len(cached))
                return cached

        unit, unit_number = INTERVAL_MAP.get(interval, (TimeframeUnit.MINUTE, 15))

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=730)

        # Paginate in ~4-month chunks (20000 bars per request is the limit)
        all_candles: list[Candle] = []
        chunk_days = 120
        current_start = start
        chunk_num = 0

        while current_start < now:
            chunk_end = min(current_start + timedelta(days=chunk_days), now)
            start_str = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")

            chunk_num += 1
            logger.info("Fetching %s chunk %d: %s to %s", contract_id, chunk_num, start_str[:10], end_str[:10])

            try:
                bars = await self._client.retrieve_bars(
                    contract_id=contract_id,
                    start_time=start_str,
                    end_time=end_str,
                    unit=unit,
                    unit_number=unit_number,
                    limit=20000,
                )
                for b in bars:
                    all_candles.append(Candle(
                        ts=_parse_bar_timestamp(b.timestamp),
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=b.volume,
                    ))
                logger.info("  Got %d bars (total: %d)", len(bars), len(all_candles))
            except Exception as e:
                logger.warning("  Chunk fetch failed: %s", e)

            current_start = chunk_end

        # Deduplicate and sort
        seen = set()
        unique: list[Candle] = []
        for c in all_candles:
            if c.ts not in seen:
                seen.add(c.ts)
                unique.append(c)
        unique.sort(key=lambda c: c.ts)

        if unique:
            _save_to_cache(contract_id, interval, unique)

        logger.info("Total unique futures candles for %s: %d", contract_id, len(unique))
        return unique
