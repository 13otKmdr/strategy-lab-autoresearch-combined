"""TDD tests for cycles.py data source routing.

Verifies that the cycle runner correctly routes to ProjectX real futures data
or Twelve Data ETF proxies based on the DATA_SOURCE config.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.market import Candle


@pytest.fixture
def mock_candles():
    return [
        Candle(ts=1_700_000_000_000 + i * 900_000, open=100.0, high=101.0, low=99.0, close=100.5, volume=100.0)
        for i in range(1000)
    ]


@pytest.mark.asyncio
async def test_run_cycle_uses_projectx_when_data_source_is_projectx(mock_candles, monkeypatch):
    """When DATA_SOURCE=projectx, cycles.py should call ProjectX provider."""
    monkeypatch.setenv("DATA_SOURCE", "projectx")
    monkeypatch.setenv("TOPSTEPX_BASE_URL", "https://api.topstepx.com")
    monkeypatch.setenv("TOPSTEPX_EMAIL", "test@example.com")
    monkeypatch.setenv("TOPSTEPX_API_KEY", "test-key")

    # Reload config to pick up env
    from app import config
    monkeypatch.setattr(config, "DATA_SOURCE", "projectx")

    with patch("app.api.cycles.ProjectXMarketDataProvider") as MockProvider, \
         patch("app.api.cycles.resolve_contract_id", return_value="CON.F.US.MYM.M26") as mock_resolve, \
         patch("app.api.cycles.fetch_2y_candles", new=AsyncMock(return_value=[])) as mock_twelve, \
         patch("app.api.cycles.scout_all_assets") as mock_scout, \
         patch("app.api.cycles.generate_for_asset", return_value=[]) as mock_gen, \
         patch("app.api.cycles.storage") as mock_storage:

        mock_provider = MagicMock()
        mock_provider.fetch_2y_candles = AsyncMock(return_value=mock_candles)
        MockProvider.return_value = mock_provider

        mock_scout.return_value = {
            "MYM": MagicMock(regime="ranging", direction_bias="neutral", strength=0.5,
                             instrument="MYM", symbol="MYM", to_dict=lambda: {}),
        }

        from app.api.cycles import run_cycle
        await run_cycle()

        # ProjectX provider should have been instantiated
        MockProvider.assert_called_once()
        # Contract resolver should have been called
        mock_resolve.assert_called_with("MYM")
        # fetch_2y_candles on the provider should have been called
        mock_provider.fetch_2y_candles.assert_called_with("CON.F.US.MYM.M26", "15min", use_cache=True)
        # Twelve Data should NOT have been called
        mock_twelve.assert_not_called()


@pytest.mark.asyncio
async def test_run_cycle_uses_twelvedata_when_data_source_is_twelvedata(mock_candles, monkeypatch):
    """When DATA_SOURCE=twelvedata, cycles.py should use Twelve Data."""
    monkeypatch.setenv("DATA_SOURCE", "twelvedata")

    from app import config
    monkeypatch.setattr("app.api.cycles.config.DATA_SOURCE", "twelvedata")

    with patch("app.api.cycles.ProjectXMarketDataProvider") as MockProvider, \
         patch("app.api.cycles.fetch_2y_candles", new=AsyncMock(return_value=mock_candles)) as mock_twelve, \
         patch("app.api.cycles.scout_all_assets") as mock_scout, \
         patch("app.api.cycles.generate_for_asset", return_value=[]) as mock_gen, \
         patch("app.api.cycles.storage") as mock_storage:

        mock_scout.return_value = {
            "MYM": MagicMock(regime="ranging", direction_bias="neutral", strength=0.5,
                             instrument="MYM", symbol="MYM", to_dict=lambda: {}),
        }

        from app.api.cycles import run_cycle
        await run_cycle()

        # Twelve Data should have been called
        mock_twelve.assert_called_with("MYM", "15min", use_cache=True)
        # ProjectX provider should NOT have been instantiated
        MockProvider.assert_not_called()


@pytest.mark.asyncio
async def test_run_cycle_falls_back_to_mock_when_all_sources_fail(monkeypatch):
    """If both data sources fail, cycle should fall back to mock data."""
    monkeypatch.setenv("DATA_SOURCE", "projectx")

    from app import config
    monkeypatch.setattr("app.api.cycles.config.DATA_SOURCE", "projectx")

    with patch("app.api.cycles.ProjectXMarketDataProvider") as MockProvider, \
         patch("app.api.cycles.generate_mock_candles") as mock_mock_gen, \
         patch("app.api.cycles.scout_all_assets") as mock_scout, \
         patch("app.api.cycles.generate_for_asset", return_value=[]) as mock_gen, \
         patch("app.api.cycles.storage") as mock_storage:

        mock_provider = MagicMock()
        mock_provider.fetch_2y_candles = AsyncMock(return_value=[])
        mock_provider.fetch_candles = AsyncMock(return_value=[])
        MockProvider.return_value = mock_provider

        mock_scout.return_value = {
            "MYM": MagicMock(regime="ranging", direction_bias="neutral", strength=0.5,
                             instrument="MYM", symbol="MYM", to_dict=lambda: {}),
        }

        from app.api.cycles import run_cycle
        await run_cycle()

        # Should have fallen back to mock data generation
        mock_mock_gen.assert_called_once()
        args, kwargs = mock_mock_gen.call_args
        assert kwargs.get("num_candles") == 5000
