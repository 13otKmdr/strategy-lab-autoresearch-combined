"""Futures contract resolver — maps instrument symbols to front-month ProjectX contract IDs.

CME/CBOT equity index micros expire quarterly (Mar/Jun/Sep/Dec).
This module computes the active front-month contract based on the current date
with configurable rollover days before expiry.

Usage:
    from app.data.contract_resolver import resolve_contract_id
    contract_id = resolve_contract_id("MYM")  # "CON.F.US.MYM.M26"
"""
from __future__ import annotations

import os
from calendar import monthcalendar
from datetime import date, timedelta

# ── Month code mapping ───────────────────────────────────────────────────────
MONTH_CODE_MAP: dict[int, str] = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

CODE_MONTH_MAP: dict[str, int] = {v: k for k, v in MONTH_CODE_MAP.items()}

# Quarterly expiry months for CME equity index micros
QUARTERLY_MONTHS: tuple[int, ...] = (3, 6, 9, 12)

# Default rollover: switch to next contract 8 calendar days before expiry
DEFAULT_ROLLOVER_DAYS: int = int(os.getenv("CONTRACT_ROLLOVER_DAYS", "8"))

# Env overrides — e.g. MYM_CONTRACT_MONTH=M26
_OVERRIDES: dict[str, str] = {
    sym: os.getenv(f"{sym}_CONTRACT_MONTH", "")
    for sym in ("MES", "MNQ", "MYM", "MGC", "MCL")
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> date:
    """Return the date of the 3rd Friday in the given month/year."""
    cal = monthcalendar(year, month)
    fridays = [week[4] for week in cal if week[4] != 0]
    return date(year, month, fridays[2])


def _expiry_date(year: int, month: int) -> date:
    """Expiry date for CME equity index micro futures (3rd Friday)."""
    return _third_friday(year, month)


def _front_month(today: date | None = None, rollover_days: int = DEFAULT_ROLLOVER_DAYS) -> tuple[int, int]:
    """Determine the current front-month year and month.

    Returns (year, month) of the active contract.
    """
    today = today or date.today()

    # Find the current quarterly cycle
    current_year = today.year

    # Look at quarterly months in order
    for i, expiry_month in enumerate(QUARTERLY_MONTHS):
        expiry = _expiry_date(current_year, expiry_month)
        rollover = expiry - timedelta(days=rollover_days)

        if today <= rollover:
            # We're before the rollover — this contract is still front month
            return current_year, expiry_month

    # Past the December rollover — front month is March of next year
    return current_year + 1, 3


def _build_month_code(year: int, month: int) -> str:
    """Build the month-year suffix like 'M26' from year and month."""
    code = MONTH_CODE_MAP[month]
    yy = str(year)[-2:]
    return f"{code}{yy}"


# ── Public API ───────────────────────────────────────────────────────────────

def resolve_contract_id(
    symbol: str,
    today: date | None = None,
    rollover_days: int = DEFAULT_ROLLOVER_DAYS,
) -> str:
    """Resolve an instrument symbol to a full ProjectX contract ID.

    Args:
        symbol: e.g. "MYM", "MES", "MNQ"
        today: reference date (defaults to today); override for backtesting
        rollover_days: days before expiry to roll to next contract

    Returns:
        Full contract ID like "CON.F.US.MYM.M26"

    Raises:
        ValueError: if symbol is unknown
    """
    from app.models.market import INSTRUMENTS

    spec = INSTRUMENTS.get(symbol.upper())
    if spec is None:
        raise ValueError(f"Unknown instrument symbol: {symbol}")

    base = spec["projectx_contract_id"]

    # Check env override first
    override = _OVERRIDES.get(symbol.upper(), "")
    if override:
        return f"{base}.{override}"

    year, month = _front_month(today, rollover_days)
    suffix = _build_month_code(year, month)
    return f"{base}.{suffix}"


def get_contract_month(symbol: str, today: date | None = None) -> str:
    """Return just the month-year suffix (e.g. 'M26') for a symbol."""
    full = resolve_contract_id(symbol, today)
    return full.split(".")[-1]
