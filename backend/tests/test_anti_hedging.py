"""Tests for the anti-hedging guard in prop_done_right.check_anti_hedging."""

from app.engine.prop_done_right import check_anti_hedging


def test_flat_allows_long():
    """No position (flat) allows entering a long."""
    decision = check_anti_hedging("flat", "long")
    assert decision.allowed is True
    assert decision.action == "allow"


def test_flat_allows_short():
    """No position (flat) allows entering a short."""
    decision = check_anti_hedging("flat", "short")
    assert decision.allowed is True
    assert decision.action == "allow"


def test_long_blocks_short():
    """Existing long position blocks a short entry (anti-hedging)."""
    decision = check_anti_hedging("long", "short")
    assert decision.allowed is False
    assert decision.action == "block_entry"
    assert "anti-hedging" in decision.reason.lower()


def test_short_blocks_long():
    """Existing short position blocks a long entry (anti-hedging)."""
    decision = check_anti_hedging("short", "long")
    assert decision.allowed is False
    assert decision.action == "block_entry"
    assert "anti-hedging" in decision.reason.lower()
