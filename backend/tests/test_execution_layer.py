"""TDD tests for execution layer safety gates (Task 9).

These tests prove the execution layer FAILS CLOSED:
- Live mode is blocked by default
- Dry-run never calls the broker order endpoint
- Read-only mode refuses order placement
- Kill switch blocks all activity
- TradeIntent requires protective brackets
- Audit log records every decision
- Risk daemon enforces all pre-trade checks
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.execution.trade_intent import TradeIntent
from app.execution.execution_mode import ExecutionMode, require_live_gates
from app.execution.audit_log import AuditLogger
from app.execution.kill_switch import KillSwitch
from app.execution.order_state import OrderState, OrderStateMachine
from app.execution.risk_daemon import RiskDaemon, RiskCheckResult
from app.execution.broker_adapter import (
    BrokerAdapter, PaperBroker, ProjectXReadonlyAdapter,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mym_intent(stop_ticks: int = 10, target_ticks: int = 20) -> TradeIntent:
    return TradeIntent(
        strategy_id="orb-001",
        symbol="MYM",
        contract_id="CON.F.US.MYM.M26",
        direction="long",
        quantity=1,
        entry_type="market",
        stop_loss_ticks=stop_ticks,
        take_profit_ticks=target_ticks,
        custom_tag="orb-001-001",
    )


# ── TradeIntent ──────────────────────────────────────────────────────────────

class TestTradeIntent:
    """TradeIntent is the broker-neutral order model."""

    def test_requires_protective_stop(self):
        """A trade without a stop should be invalid."""
        intent = TradeIntent(
            strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
            direction="long", quantity=1, entry_type="market",
            stop_loss_ticks=0, take_profit_ticks=20, custom_tag="t1",
        )
        assert not intent.has_protective_stop()

    def test_valid_intent_has_stop(self):
        """A trade with stop_loss_ticks > 0 is valid."""
        intent = _mym_intent()
        assert intent.has_protective_stop()

    def test_quantity_must_be_positive_integer(self):
        """Fractional contracts are rejected."""
        with pytest.raises(ValueError):
            TradeIntent(
                strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
                direction="long", quantity=0.5, entry_type="market",
                stop_loss_ticks=10, take_profit_ticks=20, custom_tag="t1",
            )

    def test_quantity_must_be_at_least_one(self):
        with pytest.raises(ValueError):
            TradeIntent(
                strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
                direction="long", quantity=0, entry_type="market",
                stop_loss_ticks=10, take_profit_ticks=20, custom_tag="t1",
            )

    def test_direction_must_be_long_or_short(self):
        with pytest.raises(ValueError):
            TradeIntent(
                strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
                direction="sideways", quantity=1, entry_type="market",
                stop_loss_ticks=10, take_profit_ticks=20, custom_tag="t1",
            )


# ── Execution Mode ───────────────────────────────────────────────────────────

class TestExecutionMode:
    """Execution modes enforce the safety ladder."""

    def test_default_mode_is_read_only(self):
        """Without explicit configuration, mode must be READ_ONLY."""
        mode = ExecutionMode.from_string(None)
        assert mode == ExecutionMode.READ_ONLY

    def test_read_only_blocks_orders(self):
        """READ_ONLY mode must refuse all order placement."""
        mode = ExecutionMode.READ_ONLY
        assert not mode.can_place_orders

    def test_dry_run_does_not_call_broker(self):
        """DRY_RUN mode can simulate but must not hit the real API."""
        mode = ExecutionMode.DRY_RUN
        assert mode.can_place_orders is False
        assert mode.is_simulated is True

    def test_paper_can_place_simulated_orders(self):
        """PAPER mode places simulated orders."""
        mode = ExecutionMode.PAPER
        assert mode.can_place_orders is True
        assert mode.is_simulated is True

    def test_live_requires_all_gates(self):
        """LIVE mode requires explicit arming and all safety gates."""
        with pytest.raises(RuntimeError, match="live gate"):
            require_live_gates(
                mode=ExecutionMode.LIVE,
                account_id="22096140",
                strategy_approved=False,
                kill_switch_active=False,
                has_protective_bracket=True,
            )

    def test_live_passes_when_all_gates_met(self):
        """LIVE mode passes when every safety condition is satisfied."""
        # Should not raise
        require_live_gates(
            mode=ExecutionMode.LIVE,
            account_id="22096140",
            strategy_approved=True,
            kill_switch_active=False,
            has_protective_bracket=True,
            arming_token="arm-2026-04-23",
            live_feature_flag=True,
            allowlisted_account_ids={"22096140"},
        )

    def test_live_blocked_by_kill_switch(self):
        """LIVE mode must be blocked if kill switch is active."""
        with pytest.raises(RuntimeError, match="kill switch"):
            require_live_gates(
                mode=ExecutionMode.LIVE,
                account_id="22096140",
                strategy_approved=True,
                kill_switch_active=True,
                has_protective_bracket=True,
                arming_token="arm-2026-04-23",
                live_feature_flag=True,
                allowlisted_account_ids={"22096140"},
            )

    def test_live_blocked_without_bracket(self):
        """LIVE mode must refuse orders without protective brackets."""
        with pytest.raises(RuntimeError, match="bracket"):
            require_live_gates(
                mode=ExecutionMode.LIVE,
                account_id="22096140",
                strategy_approved=True,
                kill_switch_active=False,
                has_protective_bracket=False,
                arming_token="arm-2026-04-23",
                live_feature_flag=True,
                allowlisted_account_ids={"22096140"},
            )

    def test_live_blocked_for_non_allowlisted_account(self):
        """Only explicitly allowlisted accounts can trade live."""
        with pytest.raises(RuntimeError, match="allowlist"):
            require_live_gates(
                mode=ExecutionMode.LIVE,
                account_id="99999999",
                strategy_approved=True,
                kill_switch_active=False,
                has_protective_bracket=True,
                arming_token="arm-2026-04-23",
                live_feature_flag=True,
                allowlisted_account_ids={"22096140"},
            )


# ── Kill Switch ──────────────────────────────────────────────────────────────

class TestKillSwitch:
    """Kill switch provides emergency halt."""

    def test_initial_state_is_inactive(self):
        ks = KillSwitch()
        assert not ks.is_active

    def test_activate_blocks_trading(self):
        ks = KillSwitch()
        ks.activate("daily loss limit hit")
        assert ks.is_active
        assert ks.reason == "daily loss limit hit"

    def test_deactivate_restores_trading(self):
        ks = KillSwitch()
        ks.activate("test")
        ks.deactivate()
        assert not ks.is_active

    def test_cannot_trade_when_active(self):
        ks = KillSwitch()
        ks.activate("emergency")
        assert not ks.allows_trading()


# ── Audit Log ────────────────────────────────────────────────────────────────

class TestAuditLog:
    """Append-only audit trail for all execution decisions."""

    def test_log_entry_written(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            logger = AuditLogger(path)
            logger.log("TRADE_INTENT", {"symbol": "MYM", "direction": "long", "qty": 1})

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["event_type"] == "TRADE_INTENT"
            assert entry["data"]["symbol"] == "MYM"
            assert "timestamp" in entry
        finally:
            os.unlink(path)

    def test_multiple_entries_are_appended(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            logger = AuditLogger(path)
            logger.log("GATE_CHECK", {"result": "blocked"})
            logger.log("GATE_CHECK", {"result": "allowed"})

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
        finally:
            os.unlink(path)


# ── Order State Machine ─────────────────────────────────────────────────────

class TestOrderStateMachine:
    """Order lifecycle state machine."""

    def test_valid_transitions(self):
        osm = OrderStateMachine()
        order = osm.create_order("ord-001", _mym_intent())
        assert order.state == OrderState.PENDING

        osm.transition(order, OrderState.SUBMITTED)
        assert order.state == OrderState.SUBMITTED

        osm.transition(order, OrderState.ACCEPTED)
        assert order.state == OrderState.ACCEPTED

        osm.transition(order, OrderState.FILLED)
        assert order.state == OrderState.FILLED

    def test_invalid_transition_rejected(self):
        osm = OrderStateMachine()
        order = osm.create_order("ord-001", _mym_intent())
        with pytest.raises(ValueError, match="invalid transition"):
            osm.transition(order, OrderState.FILLED)  # skip SUBMITTED

    def test_cancelled_state(self):
        osm = OrderStateMachine()
        order = osm.create_order("ord-001", _mym_intent())
        osm.transition(order, OrderState.CANCELLED)
        assert order.state == OrderState.CANCELLED

    def test_rejected_state(self):
        osm = OrderStateMachine()
        order = osm.create_order("ord-001", _mym_intent())
        osm.transition(order, OrderState.REJECTED)
        assert order.state == OrderState.REJECTED


# ── Risk Daemon ──────────────────────────────────────────────────────────────

class TestRiskDaemon:
    """Pre-trade risk checks."""

    def test_passes_with_valid_intent(self):
        daemon = RiskDaemon()
        intent = _mym_intent()
        result = daemon.check(intent, day_pnl=0, consecutive_losses=0)
        assert result.allowed

    def test_blocks_without_protective_stop(self):
        daemon = RiskDaemon()
        intent = TradeIntent(
            strategy_id="s1", symbol="MYM", contract_id="CON.F.US.MYM.M26",
            direction="long", quantity=1, entry_type="market",
            stop_loss_ticks=0, take_profit_ticks=20, custom_tag="t1",
        )
        result = daemon.check(intent, day_pnl=0, consecutive_losses=0)
        assert not result.allowed
        assert "stop" in result.reason.lower()

    def test_blocks_when_drb_exceeded(self):
        """Daily risk budget hit → block new entries."""
        daemon = RiskDaemon(daily_risk_budget=200.0)
        intent = _mym_intent()
        result = daemon.check(intent, day_pnl=-250, consecutive_losses=0)
        assert not result.allowed
        assert "drb" in result.reason.lower() or "risk budget" in result.reason.lower()

    def test_blocks_on_consecutive_losses(self):
        """After 2 consecutive losses, block new entries."""
        daemon = RiskDaemon(max_consecutive_losses=2)
        intent = _mym_intent()
        result = daemon.check(intent, day_pnl=0, consecutive_losses=2)
        assert not result.allowed
        assert "consecutive" in result.reason.lower()

    def test_blocks_mini_contracts(self):
        """Mini contracts (YM, ES, NQ) must be blocked."""
        daemon = RiskDaemon()
        intent = TradeIntent(
            strategy_id="s1", symbol="YM", contract_id="CON.F.US.YM.M26",
            direction="long", quantity=1, entry_type="market",
            stop_loss_ticks=5, take_profit_ticks=10, custom_tag="t1",
        )
        result = daemon.check(intent, day_pnl=0, consecutive_losses=0)
        assert not result.allowed
        assert "mini" in result.reason.lower() or "micro" in result.reason.lower()


# ── Broker Adapters ──────────────────────────────────────────────────────────

class TestPaperBroker:
    """Paper broker simulates fills without hitting any API."""

    def test_paper_broker_simulates_fill(self):
        broker = PaperBroker()
        intent = _mym_intent()
        result = broker.submit(intent)
        assert result.filled
        assert result.fill_price > 0
        assert result.simulated

    def test_paper_broker_never_calls_real_api(self):
        """Paper broker should have no HTTP dependency."""
        broker = PaperBroker()
        assert broker.is_simulated


class TestProjectXReadonlyAdapter:
    """Read-only adapter can query account/positions but never places orders."""

    def test_readonly_refuses_order_submission(self):
        adapter = ProjectXReadonlyAdapter()
        intent = _mym_intent()
        with pytest.raises(RuntimeError, match="read.only"):
            adapter.submit(intent)

    def test_readonly_can_query_positions(self):
        """Read-only adapter should expose position/account query methods."""
        adapter = ProjectXReadonlyAdapter()
        assert hasattr(adapter, "get_positions")
        assert hasattr(adapter, "get_account")
