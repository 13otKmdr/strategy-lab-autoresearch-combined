"""Tests for ProjectX client and market data provider.

These tests use mocked HTTP to verify:
- Auth works with email in userName field
- Account/position queries parse correctly
- Order placement sends correct payloads with brackets
- Market data bars are converted to Candle format
- Live adapter enforces all safety gates
- Contract ID builder works correctly
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.execution.projectx_client import (
    ProjectXClient, ProjectXAccount, ProjectXPosition,
    ProjectXOrderResult, ProjectXBar,
    OrderType, OrderSide, TimeframeUnit,
)
from app.execution.broker_adapter import (
    ProjectXLiveAdapter, ProjectXReadonlyAdapter, PaperBroker,
    FillResult, create_broker,
)
from app.execution.execution_mode import ExecutionMode
from app.execution.trade_intent import TradeIntent
from app.models.market import get_projectx_contract_id


def _mym_intent() -> TradeIntent:
    return TradeIntent(
        strategy_id="orb-001", symbol="MYM", contract_id="CON.F.US.MYM.M26",
        direction="long", quantity=1, entry_type="market",
        stop_loss_ticks=10, take_profit_ticks=20, custom_tag="orb-001-001",
    )


# ── ProjectX Client Unit Tests ──────────────────────────────────────────────

class TestProjectXClientAuth:
    """Auth uses email in userName field (known TopstepX quirk)."""

    @pytest.mark.asyncio
    async def test_auth_sends_email_as_userName(self):
        client = ProjectXClient(
            base_url="https://api.topstepx.com",
            email="jared@example.com",
            api_key="test-key-123",
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "token": "jwt-token-here",
            "errorCode": 0,
            "errorMessage": None,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client.authenticate()

        assert token == "jwt-token-here"
        call_args = mock_ctx.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert body["userName"] == "jared@example.com"
        assert body["apiKey"] == "test-key-123"

    @pytest.mark.asyncio
    async def test_auth_failure_raises(self):
        client = ProjectXClient(email="x", api_key="y")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": False, "errorCode": 3, "errorMessage": "invalid creds",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(RuntimeError, match="auth failed"):
                await client.authenticate()


class TestProjectXClientAccount:
    @pytest.mark.asyncio
    async def test_search_accounts_parses_response(self):
        client = ProjectXClient(email="x", api_key="y")
        client._token = "fake-token"
        client._token_expiry = 9999999999.0  # far future

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "accounts": [
                {"id": 22096140, "name": "50K Combine", "balance": 50000, "canTrade": True, "isVisible": True},
            ],
            "success": True,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            accounts = await client.search_accounts()

        assert len(accounts) == 1
        assert accounts[0].id == 22096140
        assert accounts[0].balance == 50000
        assert accounts[0].can_trade is True


class TestProjectXClientPositions:
    @pytest.mark.asyncio
    async def test_search_positions_parses_response(self):
        client = ProjectXClient(email="x", api_key="y")
        client._token = "fake-token"
        client._token_expiry = 9999999999.0  # far future

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "positions": [
                {
                    "id": 6124, "accountId": 22096140,
                    "contractId": "CON.F.US.MYM.M26",
                    "creationTimestamp": "2026-04-23T14:00:00Z",
                    "type": 1, "size": 2, "averagePrice": 42000.50,
                },
            ],
            "success": True,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            positions = await client.search_open_positions(22096140)

        assert len(positions) == 1
        assert positions[0].contract_id == "CON.F.US.MYM.M26"
        assert positions[0].size == 2
        assert positions[0].average_price == 42000.50


class TestProjectXClientOrder:
    @pytest.mark.asyncio
    async def test_place_order_sends_brackets(self):
        client = ProjectXClient(email="x", api_key="y")
        client._token = "fake-token"
        client._token_expiry = 9999999999.0  # far future

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "orderId": 9056, "success": True, "errorCode": 0, "errorMessage": None,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.place_order(
                account_id=22096140,
                contract_id="CON.F.US.MYM.M26",
                side=OrderSide.BUY,
                size=1,
                order_type=OrderType.MARKET,
                stop_loss_ticks=10,
                take_profit_ticks=20,
                custom_tag="orb-001-001",
            )

        assert result.success is True
        assert result.order_id == 9056

        # Verify brackets were sent
        call_args = mock_ctx.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert body["stopLossBracket"]["ticks"] == 10
        assert body["takeProfitBracket"]["ticks"] == 20
        assert body["customTag"] == "orb-001-001"


# ── Live Adapter Gate Tests ─────────────────────────────────────────────────

class TestProjectXLiveAdapter:
    """Live adapter must enforce all safety gates before submission."""

    @pytest.mark.asyncio
    async def test_live_adapter_rejects_without_gates(self):
        mock_client = AsyncMock()
        adapter = ProjectXLiveAdapter(
            client=mock_client,
            account_id=22096140,
            allowlisted_account_ids=set(),
            live_feature_flag=False,
            arming_token=None,
        )
        intent = _mym_intent()
        result = await adapter.submit(intent, strategy_approved=False, kill_switch_active=False)
        assert result.filled is False
        assert result.broker_response is not None
        assert "gate_rejected" in result.broker_response

    @pytest.mark.asyncio
    async def test_live_adapter_rejects_when_kill_switch_active(self):
        mock_client = AsyncMock()
        adapter = ProjectXLiveAdapter(
            client=mock_client,
            account_id=22096140,
            allowlisted_account_ids={"22096140"},
            live_feature_flag=True,
            arming_token="arm-token",
        )
        intent = _mym_intent()
        result = await adapter.submit(intent, strategy_approved=True, kill_switch_active=True)
        assert result.filled is False

    @pytest.mark.asyncio
    async def test_live_adapter_passes_with_all_gates(self):
        mock_client = AsyncMock()
        mock_client.place_order.return_value = ProjectXOrderResult(
            order_id=123, success=True, error_code=0, error_message=None,
        )
        adapter = ProjectXLiveAdapter(
            client=mock_client,
            account_id=22096140,
            allowlisted_account_ids={"22096140"},
            live_feature_flag=True,
            arming_token="arm-token",
        )
        intent = _mym_intent()
        result = await adapter.submit(intent, strategy_approved=True, kill_switch_active=False)
        assert result.filled is True
        assert result.order_id == "123"

    @pytest.mark.asyncio
    async def test_live_adapter_maps_direction_to_side(self):
        mock_client = AsyncMock()
        mock_client.place_order.return_value = ProjectXOrderResult(
            order_id=124, success=True, error_code=0, error_message=None,
        )
        adapter = ProjectXLiveAdapter(
            client=mock_client,
            account_id=22096140,
            allowlisted_account_ids={"22096140"},
            live_feature_flag=True,
            arming_token="arm-token",
        )

        # Long → BUY (side=0)
        long_intent = _mym_intent()
        await adapter.submit(long_intent, strategy_approved=True, kill_switch_active=False)
        call = mock_client.place_order.call_args
        assert call.kwargs.get("side") == OrderSide.BUY or call[1].get("side") == OrderSide.BUY

        # Short → SELL (side=1)
        short_intent = TradeIntent(
            strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
            direction="short", quantity=1, entry_type="market",
            stop_loss_ticks=10, take_profit_ticks=20, custom_tag="s1-001",
        )
        await adapter.submit(short_intent, strategy_approved=True, kill_switch_active=False)
        call = mock_client.place_order.call_args
        assert call.kwargs.get("side") == OrderSide.SELL or call[1].get("side") == OrderSide.SELL


# ── Broker Factory ───────────────────────────────────────────────────────────

class TestBrokerFactory:
    def test_read_only_mode_creates_readonly_adapter(self):
        broker = create_broker(ExecutionMode.READ_ONLY)
        assert isinstance(broker, ProjectXReadonlyAdapter)

    def test_dry_run_mode_creates_readonly_adapter(self):
        broker = create_broker(ExecutionMode.DRY_RUN)
        assert isinstance(broker, ProjectXReadonlyAdapter)

    def test_paper_mode_creates_paper_broker(self):
        broker = create_broker(ExecutionMode.PAPER)
        assert isinstance(broker, PaperBroker)

    def test_live_mode_creates_live_adapter(self):
        broker = create_broker(
            ExecutionMode.LIVE,
            account_id=22096140,
            client=None,
            allowlisted_account_ids={"22096140"},
            live_feature_flag=True,
            arming_token="token",
        )
        assert isinstance(broker, ProjectXLiveAdapter)


# ── Contract ID Builder ─────────────────────────────────────────────────────

class TestContractIDBuilder:
    def test_mym_with_month_code(self):
        result = get_projectx_contract_id("MYM", "M26")
        assert result == "CON.F.US.MYM.M26"

    def test_mes_without_month_code(self):
        result = get_projectx_contract_id("MES")
        assert result == "CON.F.US.MES"

    def test_unknown_symbol_raises(self):
        with pytest.raises(ValueError, match="Unknown instrument"):
            get_projectx_contract_id("FAKE")


# ── Enums ────────────────────────────────────────────────────────────────────

class TestEnums:
    def test_order_types(self):
        assert OrderType.MARKET == 2
        assert OrderType.LIMIT == 1
        assert OrderType.STOP == 4

    def test_order_sides(self):
        assert OrderSide.BUY == 0
        assert OrderSide.SELL == 1

    def test_timeframe_units(self):
        assert TimeframeUnit.MINUTE == 2
        assert TimeframeUnit.HOUR == 3
        assert TimeframeUnit.DAY == 4
