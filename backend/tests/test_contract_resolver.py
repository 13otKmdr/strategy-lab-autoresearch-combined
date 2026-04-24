"""TDD tests for contract_resolver.py.

Ensures instrument symbols map correctly to front-month ProjectX contract IDs
with proper rollover logic and env overrides.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from app.data.contract_resolver import (
    _build_month_code,
    _front_month,
    _third_friday,
    get_contract_month,
    resolve_contract_id,
)
from app.models.market import INSTRUMENTS


# ── resolve_contract_id ──────────────────────────────────────────────────────

def test_resolve_known_symbols():
    """All configured instruments must resolve without error."""
    for symbol in INSTRUMENTS:
        cid = resolve_contract_id(symbol)
        assert cid.startswith("CON.F.US.")
        assert len(cid.split(".")[-1]) == 3  # e.g. M26


def test_resolve_mym_returns_correct_base():
    cid = resolve_contract_id("MYM")
    assert cid.startswith("CON.F.US.MYM.")


def test_resolve_unknown_symbol_raises():
    with pytest.raises(ValueError, match="Unknown instrument symbol: XYZ"):
        resolve_contract_id("XYZ")


# ── Front-month logic ────────────────────────────────────────────────────────

def test_front_month_early_in_quarter():
    """Well before expiry, front month should be the current quarter."""
    # April 1, 2026 — June contract (M26) should be front month
    today = date(2026, 4, 1)
    year, month = _front_month(today, rollover_days=8)
    assert month == 6
    assert year == 2026


def test_front_month_after_rollover():
    """After rollover, front month should be next quarter."""
    # June 20, 2026 — past June expiry (3rd Friday is June 19), so Sep (U26)
    today = date(2026, 6, 20)
    year, month = _front_month(today, rollover_days=8)
    assert month == 9
    assert year == 2026


def test_front_month_year_rollover():
    """After December rollover, front month should be March of next year."""
    # December 20, 2026 — past Dec expiry, so March 2027 (H27)
    today = date(2026, 12, 20)
    year, month = _front_month(today, rollover_days=8)
    assert month == 3
    assert year == 2027


# ── Month code builder ───────────────────────────────────────────────────────

def test_build_month_code_june_2026():
    assert _build_month_code(2026, 6) == "M26"


def test_build_month_code_march_2027():
    assert _build_month_code(2027, 3) == "H27"


def test_build_month_code_december_2025():
    assert _build_month_code(2025, 12) == "Z25"


# ── 3rd Friday helper ────────────────────────────────────────────────────────

def test_third_friday_june_2026():
    """June 2026 3rd Friday is the 19th."""
    assert _third_friday(2026, 6) == date(2026, 6, 19)


def test_third_friday_march_2026():
    """March 2026 3rd Friday is the 20th."""
    assert _third_friday(2026, 3) == date(2026, 3, 20)


# ── Env override ─────────────────────────────────────────────────────────────

def test_env_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("MYM_CONTRACT_MONTH", "U25")
    # Re-import to pick up the new env var
    from app.data import contract_resolver as cr
    # Force re-evaluation of overrides
    cr._OVERRIDES["MYM"] = "U25"
    cid = resolve_contract_id("MYM")
    assert cid.endswith(".U25")
    # Clean up
    cr._OVERRIDES["MYM"] = ""


# ── get_contract_month ───────────────────────────────────────────────────────

def test_get_contract_month_returns_suffix():
    suffix = get_contract_month("MYM", today=date(2026, 4, 1))
    assert suffix == "M26"
