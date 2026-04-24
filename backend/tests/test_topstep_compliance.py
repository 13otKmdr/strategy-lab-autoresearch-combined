"""TDD tests for Topstep compliance validation on generated strategies.

Tests prove that validate_strategy() correctly enforces all Topstep-specific
rules that the generator does not natively enforce:
  - Min hold time (at least 1 bar / 15 min)
  - Max hold time (no open-ended holds)
  - Flat-by-close (only RTH sessions allowed)
  - No overnight / extended hours
  - Anti-hedging (no opposing direction capability)
  - News event avoidance (fundamental filters required)
"""
from __future__ import annotations

import pytest

from app.engine.topstep_compliance import (
    ComplianceResult,
    TopstepComplianceConfig,
    validate_strategy,
    validate_strategy_batch,
)
from app.models.strategy import StrategyDefinition


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_strategy(**overrides) -> StrategyDefinition:
    """Build a minimal StrategyDefinition with Topstep-compliant defaults."""
    exit_rules = overrides.pop("exit_rules", None)
    defaults = dict(
        strategy_id="test-strat-001",
        strategy_name="TestStrategy-MYM-001",
        strategy_type="trend_following",
        market_type="futures",
        thesis_summary="Test strategy",
        indicators_used=[{"type": "EMA", "params": {"period": 20}}],
        candlestick_patterns_used=[],
        timeframe_stack=["15min"],
        entry_rules={"trigger": "PRICE_ABOVE_EMA", "filter": "NONE", "direction": "long", "description": "test"},
        exit_rules={
            "stop_loss": {"type": "atr_multiple", "value": 1.5},
            "take_profit": {"type": "r_multiple", "value": 2.0},
            "trailing_stop_atr": None,
            "time_exit_bars": 16,
        },
        stop_loss_logic={"type": "atr_multiple", "value": 1.5},
        take_profit_logic={"type": "r_multiple", "value": 2.0},
        trailing_stop_or_break_even_logic={"type": "none"},
        session_filters={"allowed_sessions": ["us_regular"], "description": "US Regular Only"},
        volatility_filters={"min_atr_percentile": 0, "max_atr_percentile": 100, "description": "No filter"},
        fundamental_filters_if_any={"avoid_fomc": True, "avoid_nfp": True},
        intended_asset_classes=["MYM"],
        primary_indicator={"type": "EMA", "params": {"period": 20}},
        confirmation_indicator={"type": "EMA", "params": {"period": 50}},
        entry={"trigger": "PRICE_ABOVE_EMA", "filter": "NONE", "direction": "long"},
        exit={"stop_loss": {"type": "atr_multiple", "value": 1.5}, "take_profit": {"type": "r_multiple", "value": 2.0}, "time_exit_bars": 16},
        risk={"max_open_positions": 1},
    )
    if exit_rules is not None:
        defaults["exit_rules"] = exit_rules
        # Keep exit dict in sync for time_exit_bars
        teb = exit_rules.get("time_exit_bars")
        defaults["exit"] = dict(defaults["exit"])
        defaults["exit"]["time_exit_bars"] = teb
    defaults.update(overrides)
    return StrategyDefinition(**defaults)


# ── Test 1: Fully compliant strategy passes ─────────────────────────────────

class TestCompliantStrategy:
    def test_fully_compliant_passes(self):
        strat = _make_strategy()
        result = validate_strategy(strat)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_compliant_with_all_rth_sessions(self):
        """Strategy allowing only us_regular should pass."""
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["us_regular"], "description": "RTH only"},
        )
        result = validate_strategy(strat)
        assert result.passed is True


# ── Test 2: Min hold time enforcement ────────────────────────────────────────

class TestMinHoldTime:
    def test_no_time_exit_fails(self):
        """Strategy with time_exit_bars=None (no time exit) should fail."""
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": None,
            },
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("minimum hold" in v.lower() or "time_exit_bars" in v for v in result.violations)

    def test_zero_time_exit_fails(self):
        """time_exit_bars=0 would allow instant exit — should fail."""
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": 0,
            },
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("below minimum" in v.lower() or "time_exit_bars" in v for v in result.violations)


# ── Test 3: Max hold time enforcement ────────────────────────────────────────

class TestMaxHoldTime:
    def test_hold_too_long_fails(self):
        """Holding for 96 bars (24 hours) is too long for day trading."""
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": 96,
            },
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("exceeds maximum" in v.lower() or "overnight" in v.lower() for v in result.violations)

    def test_hold_at_limit_passes(self):
        """Holding for 26 bars (6.5 hours = 1 RTH session) should pass."""
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": 26,
            },
        )
        result = validate_strategy(strat)
        assert result.passed is True


# ── Test 4: Session filter enforcement ───────────────────────────────────────

class TestSessionFilter:
    def test_all_sessions_fails(self):
        """Session filter 'all' allows overnight trading — must fail."""
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["all"], "description": "All Sessions"},
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("session" in v.lower() for v in result.violations)

    def test_extended_hours_fails(self):
        """Extended hours session allows pre/post market — must fail."""
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["us_extended"], "description": "Extended"},
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("session" in v.lower() or "extended" in v.lower() for v in result.violations)

    def test_london_overlap_fails(self):
        """London overlap starts at 3:00 AM ET — pre-market, must fail."""
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["london_overlap"], "description": "London/NY"},
        )
        result = validate_strategy(strat)
        assert result.passed is False

    def test_multiple_with_disallowed_fails(self):
        """Mix of us_regular + us_extended still fails because extended is present."""
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["us_regular", "us_extended"], "description": "Mixed"},
        )
        result = validate_strategy(strat)
        assert result.passed is False


# ── Test 5: Anti-hedging / direction enforcement ────────────────────────────

class TestAntiHedging:
    def test_both_direction_allowed_fails(self):
        """Direction 'both' allows simultaneous long+short = hedging risk."""
        strat = _make_strategy(
            entry_rules={
                "trigger": "PRICE_ABOVE_EMA",
                "filter": "NONE",
                "direction": "both",
                "description": "Both directions",
            },
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert any("direction" in v.lower() or "hedge" in v.lower() for v in result.violations)

    def test_long_only_passes(self):
        strat = _make_strategy(
            entry_rules={
                "trigger": "PRICE_ABOVE_EMA",
                "filter": "NONE",
                "direction": "long",
                "description": "Long only",
            },
        )
        result = validate_strategy(strat)
        assert result.passed is True

    def test_short_only_passes(self):
        strat = _make_strategy(
            entry_rules={
                "trigger": "PRICE_BELOW_EMA",
                "filter": "NONE",
                "direction": "short",
                "description": "Short only",
            },
        )
        result = validate_strategy(strat)
        assert result.passed is True


# ── Test 6: Fundamental filters ──────────────────────────────────────────────

class TestFundamentalFilters:
    def test_empty_fundamental_filters_warns(self):
        """No news avoidance = WARNING, not hard fail (advisory)."""
        strat = _make_strategy(fundamental_filters_if_any={})
        result = validate_strategy(strat)
        # Should pass but with a warning
        assert result.passed is True
        assert any("news" in w.lower() or "fomc" in w.lower() or "nfp" in w.lower() for w in result.warnings)

    def test_partial_filters_warns(self):
        """Only avoiding FOMC but not NFP = warning."""
        strat = _make_strategy(fundamental_filters_if_any={"avoid_fomc": True})
        result = validate_strategy(strat)
        assert result.passed is True
        assert any("nfp" in w.lower() for w in result.warnings)


# ── Test 7: Multiple violations stack ────────────────────────────────────────

class TestMultipleViolations:
    def test_all_violations_reported(self):
        """Strategy with 3 violations should report all 3, not just the first."""
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": None,  # violation 1: no time exit
            },
            session_filters={"allowed_sessions": ["all"], "description": "All"},  # violation 2: all sessions
            entry_rules={
                "trigger": "PRICE_ABOVE_EMA",
                "filter": "NONE",
                "direction": "both",  # violation 3: hedging direction
                "description": "Both",
            },
        )
        result = validate_strategy(strat)
        assert result.passed is False
        assert len(result.violations) >= 3


# ── Test 8: Batch validation ─────────────────────────────────────────────────

class TestBatchValidation:
    def test_batch_filters_non_compliant(self):
        """validate_strategy_batch should return only compliant strategies."""
        compliant = _make_strategy(strategy_id="good-001")
        non_compliant = _make_strategy(
            strategy_id="bad-001",
            session_filters={"allowed_sessions": ["all"], "description": "All Sessions"},
        )
        result = validate_strategy_batch([compliant, non_compliant])
        assert len(result.passed) == 1
        assert result.passed[0].strategy_id == "good-001"
        assert len(result.failed) == 1
        assert result.failed[0].strategy.strategy_id == "bad-001"

    def test_batch_all_pass(self):
        strats = [_make_strategy(strategy_id=f"strat-{i}") for i in range(5)]
        result = validate_strategy_batch(strats)
        assert len(result.passed) == 5
        assert len(result.failed) == 0

    def test_batch_none_pass(self):
        strats = [
            _make_strategy(
                strategy_id=f"bad-{i}",
                session_filters={"allowed_sessions": ["all"], "description": "All"},
            )
            for i in range(3)
        ]
        result = validate_strategy_batch(strats)
        assert len(result.passed) == 0
        assert len(result.failed) == 3

    def test_batch_summary_counts(self):
        compliant = _make_strategy(strategy_id="good-001")
        non_compliant = _make_strategy(
            strategy_id="bad-001",
            session_filters={"allowed_sessions": ["all"], "description": "All Sessions"},
        )
        result = validate_strategy_batch([compliant, non_compliant])
        assert result.total == 2
        assert result.passed_count == 1
        assert result.failed_count == 1


# ── Test 9: Config overrides ─────────────────────────────────────────────────

class TestConfigOverrides:
    def test_custom_max_hold_time(self):
        """Config with max_hold_bars=32 should allow 30-bar hold."""
        config = TopstepComplianceConfig(max_hold_bars=32)
        strat = _make_strategy(
            exit_rules={
                "stop_loss": {"type": "atr_multiple", "value": 1.5},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "trailing_stop_atr": None,
                "time_exit_bars": 30,
            },
        )
        result = validate_strategy(strat, config=config)
        assert result.passed is True

    def test_custom_allowed_sessions(self):
        """Config allowing london_overlap should make it pass."""
        config = TopstepComplianceConfig(allowed_sessions={"us_regular", "london_overlap"})
        strat = _make_strategy(
            session_filters={"allowed_sessions": ["london_overlap"], "description": "London"},
        )
        result = validate_strategy(strat, config=config)
        assert result.passed is True
