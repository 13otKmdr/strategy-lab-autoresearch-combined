"""Tests for RESEARCH_ONLY execution guards in hedge simulator modules."""
import os
import pytest

from app.engine.hedge_simulator import RESEARCH_ONLY as SIM_RESEARCH_ONLY
from app.engine.hedge_simulator import assert_research_only as sim_assert
from app.engine.hedge_trade_model import RESEARCH_ONLY as MODEL_RESEARCH_ONLY
from app.engine.hedge_trade_model import assert_research_only as model_assert


class TestResearchOnlyConstant:
    """Verify that RESEARCH_ONLY is defined and True in both modules."""

    def test_hedge_simulator_research_only_is_true(self):
        assert SIM_RESEARCH_ONLY is True, (
            "hedge_simulator.RESEARCH_ONLY must be True"
        )

    def test_hedge_trade_model_research_only_is_true(self):
        assert MODEL_RESEARCH_ONLY is True, (
            "hedge_trade_model.RESEARCH_ONLY must be True"
        )


class TestResearchOnlyGuardLiveMode:
    """Guard must raise RuntimeError when TRADING_MODE=live."""

    @pytest.fixture(autouse=True)
    def _set_live_mode(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "live")

    def test_hedge_simulator_raises_in_live_mode(self):
        with pytest.raises(RuntimeError, match="RESEARCH_ONLY"):
            sim_assert()

    def test_hedge_trade_model_raises_in_live_mode(self):
        with pytest.raises(RuntimeError, match="RESEARCH_ONLY"):
            model_assert()


class TestResearchOnlyGuardResearchMode:
    """Guard must pass silently when TRADING_MODE=research."""

    @pytest.fixture(autouse=True)
    def _set_research_mode(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "research")

    def test_hedge_simulator_passes_in_research_mode(self):
        sim_assert()  # should not raise

    def test_hedge_trade_model_passes_in_research_mode(self):
        model_assert()  # should not raise
