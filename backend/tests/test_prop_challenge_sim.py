from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine.prop_challenge_sim import simulate_prop_challenge
from app.engine.prop_done_right import PropDoneRightConfig
from app.engine.topstep_rules import TopstepCombineRules
from app.models.backtest import Trade


BASE_TS = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)


def _trade(day: int, pnl: float, trade_no: int = 0) -> Trade:
    entry = BASE_TS + timedelta(days=day, minutes=trade_no * 10)
    exit_ = entry + timedelta(minutes=5)
    return Trade(
        entry_bar=day * 100 + trade_no,
        exit_bar=day * 100 + trade_no + 1,
        entry_price=100.0,
        exit_price=101.0,
        size=1,
        direction="long",
        pnl=pnl,
        pnl_pct=0.0,
        r_multiple=0.0,
        exit_reason="time_exit",
        entry_ts=int(entry.timestamp() * 1000),
        exit_ts=int(exit_.timestamp() * 1000),
        regime="test",
    )


def _trade_at(timestamp: datetime, pnl: float, trade_no: int = 0) -> Trade:
    exit_ = timestamp + timedelta(minutes=5)
    return Trade(
        entry_bar=trade_no,
        exit_bar=trade_no + 1,
        entry_price=100.0,
        exit_price=101.0,
        size=1,
        direction="long",
        pnl=pnl,
        pnl_pct=0.0,
        r_multiple=0.0,
        exit_reason="time_exit",
        entry_ts=int(timestamp.timestamp() * 1000),
        exit_ts=int(exit_.timestamp() * 1000),
        regime="test",
    )


def test_steady_600_per_day_for_5_days_passes_topstep_50k_and_consistency():
    trades = [_trade(day, 600) for day in range(5)]

    result = simulate_prop_challenge(trades)

    assert result.outcome == "pass"
    assert result.reason == "profit target reached with Topstep consistency satisfied"
    assert result.total_profit == 3000
    assert result.days_traded == 5
    assert result.best_day_profit == 600
    assert result.consistency_passed is True
    assert result.mll_breached is False
    assert result.trades_taken == 5
    assert result.trades_skipped == 0
    assert result.mll_floor_path[0] == 48000
    assert result.mll_floor_path[-1] == 50000


def test_two_1500_days_reaches_target_but_fails_consistency():
    trades = [_trade(0, 1500), _trade(1, 1500)]

    result = simulate_prop_challenge(trades)

    assert result.outcome == "fail_consistency"
    assert "consistency" in result.reason.lower()
    assert result.total_profit == 3000
    assert result.best_day_profit == 1500
    assert result.consistency_passed is False
    assert result.trades_taken == 2


def test_daily_loss_at_or_below_drb_causes_lockout_and_skips_same_day_trades():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=None)
    trades = [_trade(0, -250, 0), _trade(0, 1000, 1)]

    result = simulate_prop_challenge(trades, prop_config=config)

    assert result.outcome == "timeout"
    assert result.total_profit == -250
    assert result.trades_taken == 1
    assert result.trades_skipped == 1
    assert result.daily_lockouts == 1
    assert result.profit_lockouts == 0
    assert list(result.day_pnls.values()) == [-250]


def test_power_of_quitting_at_2x_drb_causes_profit_lockout_and_skips_same_day_trades():
    config = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=None)
    trades = [_trade(0, 500, 0), _trade(0, 1000, 1)]

    result = simulate_prop_challenge(trades, prop_config=config)

    assert result.outcome == "timeout"
    assert result.total_profit == 500
    assert result.trades_taken == 1
    assert result.trades_skipped == 1
    assert result.daily_lockouts == 0
    assert result.profit_lockouts == 1
    assert list(result.day_pnls.values()) == [500]


def test_max_trades_per_day_skips_excess_trades():
    trades = [_trade(0, 10, 0), _trade(0, 10, 1), _trade(0, 10, 2)]

    result = simulate_prop_challenge(trades, max_trades_per_day=2)

    assert result.outcome == "timeout"
    assert result.total_profit == 20
    assert result.trades_taken == 2
    assert result.trades_skipped == 1
    assert result.day_pnls == {"2026-01-05": 20}


def test_mll_breach_results_in_fail_mll():
    trades = [_trade(0, -2001)]

    result = simulate_prop_challenge(trades)

    assert result.outcome == "fail_mll"
    assert result.mll_breached is True
    assert "maximum loss limit" in result.reason.lower()
    assert result.total_profit == -2001
    assert result.trades_taken == 1
    assert result.mll_floor_path[-1] == TopstepCombineRules.topstep_50k().initial_mll_floor


def test_empty_trade_list_times_out_without_trades():
    result = simulate_prop_challenge([])

    assert result.outcome == "timeout"
    assert result.reason == "no trades taken"
    assert result.trades_taken == 0
    assert result.trades_skipped == 0
    assert result.day_pnls == {}


def test_trades_are_sorted_before_simulation():
    trades = [_trade(2, 600), _trade(0, 600), _trade(1, 600), _trade(4, 600), _trade(3, 600)]

    result = simulate_prop_challenge(trades)

    assert result.outcome == "pass"
    assert list(result.day_pnls.values()) == [600, 600, 600, 600, 600]


def test_central_time_5pm_rolls_to_next_futures_trading_day():
    before_roll = datetime(2026, 1, 5, 22, 30, tzinfo=timezone.utc)  # 16:30 CT
    after_roll = datetime(2026, 1, 5, 23, 30, tzinfo=timezone.utc)   # 17:30 CT
    trades = [_trade_at(before_roll, 100), _trade_at(after_roll, 200, trade_no=1)]

    result = simulate_prop_challenge(trades)

    assert result.day_pnls == {"2026-01-05": 100, "2026-01-06": 200}


def test_topstep_daily_loss_limit_locks_out_when_less_strict_than_drb():
    config = PropDoneRightConfig(configured_drawdown=20_000, official_mll_amount=None)
    rules = TopstepCombineRules.topstep_50k()
    trades = [_trade(0, -1000, 0), _trade(0, 5000, 1)]

    result = simulate_prop_challenge(trades, topstep_rules=rules, prop_config=config)

    assert result.outcome == "timeout"
    assert result.total_profit == -1000
    assert result.trades_taken == 1
    assert result.trades_skipped == 1
    assert result.daily_lockouts == 1
    assert "Daily Loss Limit" in result.reason


def test_invalid_arguments_raise_value_error():
    try:
        simulate_prop_challenge([], max_trades_per_day=0)
    except ValueError as exc:
        assert "max_trades_per_day" in str(exc)
    else:
        raise AssertionError("expected max_trades_per_day ValueError")

    try:
        simulate_prop_challenge([], target_sessions=0)
    except ValueError as exc:
        assert "target_sessions" in str(exc)
    else:
        raise AssertionError("expected target_sessions ValueError")
