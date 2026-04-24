from app.engine.prop_done_right import (
    PropDoneRightConfig,
    TradeGateInput,
    evaluate_trade_gate,
    mym_micro_contracts_for_risk,
)


def test_daily_risk_budget_uses_configured_drawdown_when_no_official_limit():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=None)

    assert config.effective_drawdown == 2500
    assert config.daily_risk_budget == 250


def test_daily_risk_budget_uses_more_conservative_official_mll_when_present():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=2000)

    assert config.effective_drawdown == 2000
    assert config.daily_risk_budget == 200


def test_trade_gate_allows_only_mym_micro_by_default():
    config = PropDoneRightConfig()

    allowed = evaluate_trade_gate(
        TradeGateInput(symbol="MYM", day_pnl=0, proposed_contracts=1),
        config,
    )
    mini = evaluate_trade_gate(
        TradeGateInput(symbol="YM", day_pnl=0, proposed_contracts=1),
        config,
    )
    mnq = evaluate_trade_gate(
        TradeGateInput(symbol="MNQ", day_pnl=0, proposed_contracts=1),
        config,
    )

    assert allowed.allowed is True
    assert mini.allowed is False
    assert "micros only" in mini.reason
    assert mnq.allowed is False
    assert "MYM only" in mnq.reason


def test_trade_gate_stops_at_daily_risk_budget():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=None)

    decision = evaluate_trade_gate(
        TradeGateInput(symbol="MYM", day_pnl=-250, proposed_contracts=1),
        config,
    )

    assert decision.allowed is False
    assert decision.action == "daily_lockout"
    assert "$250.00" in decision.reason


def test_trade_gate_power_of_quitting_hard_lock_after_two_drb_profit():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=None)

    decision = evaluate_trade_gate(
        TradeGateInput(symbol="MYM", day_pnl=500, proposed_contracts=1),
        config,
    )

    assert decision.allowed is False
    assert decision.action == "profit_lockout"
    assert "Power of Quitting" in decision.reason


def test_mym_position_size_is_integer_micro_contracts():
    # MYM tick value is $0.50. A 50 tick stop risks $25/contract before fees.
    assert mym_micro_contracts_for_risk(risk_budget=100, stop_ticks=50, round_turn_fees=2.0) == 3


def test_mym_position_size_returns_zero_when_one_micro_exceeds_risk_budget():
    assert mym_micro_contracts_for_risk(risk_budget=20, stop_ticks=50, round_turn_fees=2.0) == 0
