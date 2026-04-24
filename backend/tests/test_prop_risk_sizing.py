from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np

from app.engine.prop_done_right import PropDoneRightConfig
from app.engine.prop_risk_sizing import (
    PropRiskSizingInput,
    futures_position_pnl,
    per_trade_risk_dollars,
    size_integer_micro_contracts,
)
from app.models.market import Candle
from app.models.strategy import StrategyDefinition


WARMUP = 200


def _candles(n: int = 205, close: float = 100.0) -> list[Candle]:
    start = datetime(2026, 1, 5, 13, 45, tzinfo=timezone.utc) - timedelta(minutes=15 * WARMUP)
    return [
        Candle(
            ts=int((start + timedelta(minutes=15 * i)).timestamp() * 1000),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1000,
        )
        for i in range(n)
    ]


def _strategy(symbol: str = "MYM") -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="risk-sizing-test",
        strategy_name="Risk sizing test",
        strategy_type="breakout",
        market_type="futures",
        thesis_summary="synthetic",
        indicators_used=[],
        candlestick_patterns_used=[],
        timeframe_stack=["15m"],
        entry_rules={},
        exit_rules={},
        stop_loss_logic={},
        take_profit_logic={},
        trailing_stop_or_break_even_logic={},
        session_filters={},
        volatility_filters={},
        fundamental_filters_if_any={},
        intended_asset_classes=[symbol],
        primary_indicator={"type": "RSI", "params": {"period": 14}},
        confirmation_indicator={"type": "EMA", "params": {"period": 50}},
        entry={"trigger": "RSI_OVERSOLD", "filter": "NONE"},
        exit={
            "stop_loss": {"type": "atr_multiple", "value": 2.0},
            "take_profit": {"type": "r_multiple", "value": 2.0},
        },
        risk={"max_open_positions": 1},
    )


def test_drb_multiple_converts_to_per_trade_dollars_from_official_mll():
    cfg = PropDoneRightConfig(configured_drawdown=2500, official_mll_amount=2000)

    assert cfg.daily_risk_budget == 200
    assert per_trade_risk_dollars(0.25, cfg) == 50


def test_position_sizing_returns_integer_mym_contract_for_50_tick_stop():
    sizing = size_integer_micro_contracts(
        PropRiskSizingInput(
            symbol="MYM",
            entry_price=35_000,
            stop_price=34_950,
            risk_level=0.25,
            prop_config=PropDoneRightConfig(official_mll_amount=2000),
        )
    )

    assert sizing.contracts == 1
    assert isinstance(sizing.contracts, int)
    assert sizing.per_trade_risk_dollars == 50
    assert sizing.stop_ticks == 50
    assert sizing.dollars_at_risk_per_contract == 25


def test_position_sizing_returns_zero_when_one_mym_micro_exceeds_budget():
    sizing = size_integer_micro_contracts(
        PropRiskSizingInput(
            symbol="MYM",
            entry_price=35_000,
            stop_price=34_899,
            risk_level=0.25,
            prop_config=PropDoneRightConfig(official_mll_amount=2000),
        )
    )

    assert sizing.contracts == 0
    assert sizing.skip_reason


def test_default_backtester_trade_size_is_integer_micro_contract(monkeypatch):
    from app.engine import backtester

    candles = _candles()
    strategy = _strategy()
    indicators = {"ema200": np.full(len(candles), 90.0), "atr": np.full(len(candles), 25.0)}

    monkeypatch.setattr(backtester, "compute_indicators", lambda strategy, candles: indicators)
    monkeypatch.setattr(backtester, "check_entry", lambda strategy, indicators, i: i == WARMUP)
    monkeypatch.setattr(backtester, "calc_stop_price", lambda strategy, entry, indicators, i, short=False: entry - 50)
    monkeypatch.setattr(backtester, "calc_take_profit_price", lambda strategy, entry, stop, short=False: entry + 100)

    result = backtester.run_backtest(strategy, candles, risk_pct=0.25, initial_capital=50_000)

    assert result.total_trades == 1
    assert result.trades[0].size == 1
    assert isinstance(result.trades[0].size, int)


def test_default_backtester_skips_trade_when_stop_too_wide_for_one_mym(monkeypatch):
    from app.engine import backtester

    candles = _candles()
    strategy = _strategy()
    indicators = {"ema200": np.full(len(candles), 90.0), "atr": np.full(len(candles), 100.0)}

    monkeypatch.setattr(backtester, "compute_indicators", lambda strategy, candles: indicators)
    monkeypatch.setattr(backtester, "check_entry", lambda strategy, indicators, i: i == WARMUP)
    monkeypatch.setattr(backtester, "calc_stop_price", lambda strategy, entry, indicators, i, short=False: entry - 101)
    monkeypatch.setattr(backtester, "calc_take_profit_price", lambda strategy, entry, stop, short=False: entry + 202)

    result = backtester.run_backtest(strategy, candles, risk_pct=0.25, initial_capital=50_000)

    assert result.total_trades == 0


def test_orb_backtester_uses_integer_contract_sizing(monkeypatch):
    from app.engine import orb

    candles = _candles()
    candles[WARMUP].close = 101.0
    monkeypatch.setattr(orb, "detect_opening_range", lambda *args, **kwargs: [{"range_high": 100, "range_low": 51, "start_idx": WARMUP - 2, "end_idx": WARMUP - 1, "range_size": 49}])
    monkeypatch.setattr(orb, "_atr", lambda candles, period=14: np.full(len(candles), 1.0))

    result = orb.run_orb_backtest(
        {"strategy_id": "orb-int", "direction": "long", "stop_atr_buffer": 0.0, "tp_r_multiple": 2.0, "time_exit_bars": 16},
        candles,
        risk_pct=0.25,
    )

    assert result.total_trades == 1
    assert result.trades[0].size == 1
    assert isinstance(result.trades[0].size, int)


def test_vwap_entry_helper_uses_integer_contract_sizing():
    from app.engine.vwap_reversion import _try_enter

    candles = _candles(n=1, close=100)
    candles[0].low = 50.1
    open_positions: list[dict] = []

    _try_enter(
        "long",
        candles,
        0,
        cur_close=100,
        cur_vwap=120,
        cur_atr=1,
        stop_buffer_atr=0,
        tp_mode="r_multiple_2",
        risk_pct=0.25,
        equity=50_000,
        open_positions=open_positions,
        strategy_id="vwap-int",
    )

    assert len(open_positions) == 1
    assert open_positions[0]["size"] == 1
    assert isinstance(open_positions[0]["size"], int)


def test_session_rotation_backtester_uses_integer_contract_sizing(monkeypatch):
    from app.engine import session_rotation

    candles = _candles()
    cfg = session_rotation.SessionRotationConfig()
    indicators = {"ema200": np.full(len(candles), 90.0), "atr": np.full(len(candles), 25.0)}

    monkeypatch.setattr(session_rotation, "_compute_all_session_indicators", lambda config, candles: {"morning": indicators, "midday": indicators, "afternoon": indicators})
    monkeypatch.setitem(session_rotation.ENTRY_TRIGGERS, cfg.morning_trigger, lambda indicators, i: i == WARMUP)
    monkeypatch.setitem(session_rotation.CONFIRMATIONS, cfg.morning_filter, lambda indicators, i: True)
    monkeypatch.setattr(session_rotation, "calc_stop_price", lambda strategy, entry, indicators, i, short=False: entry - 50)
    monkeypatch.setattr(session_rotation, "calc_take_profit_price", lambda strategy, entry, stop, short=False: entry + 100)

    result = session_rotation.run_session_backtest(cfg, candles, risk_pct=0.25, initial_capital=50_000)

    assert result.total_trades == 1
    assert result.trades[0].size == 1
    assert isinstance(result.trades[0].size, int)


def test_orb_backtester_skips_when_stop_too_wide_for_one_mym(monkeypatch):
    from app.engine import orb

    candles = _candles()
    candles[WARMUP].close = 101.0
    monkeypatch.setattr(
        orb,
        "detect_opening_range",
        lambda *args, **kwargs: [{"range_high": 100, "range_low": -1, "start_idx": WARMUP - 2, "end_idx": WARMUP - 1, "range_size": 101}],
    )
    monkeypatch.setattr(orb, "_atr", lambda candles, period=14: np.full(len(candles), 1.0))

    result = orb.run_orb_backtest(
        {"strategy_id": "orb-skip", "direction": "long", "stop_atr_buffer": 0.0, "tp_r_multiple": 2.0, "time_exit_bars": 16},
        candles,
        risk_pct=0.25,
    )

    assert result.total_trades == 0


def test_vwap_entry_helper_skips_when_stop_too_wide_for_one_mym():
    from app.engine.vwap_reversion import _try_enter

    candles = _candles(n=1, close=200)
    candles[0].low = 99
    open_positions: list[dict] = []

    _try_enter(
        "long",
        candles,
        0,
        cur_close=200,
        cur_vwap=220,
        cur_atr=1,
        stop_buffer_atr=0,
        tp_mode="r_multiple_2",
        risk_pct=0.25,
        equity=50_000,
        open_positions=open_positions,
        strategy_id="vwap-skip",
    )

    assert open_positions == []


def test_session_rotation_passes_config_symbol_to_sizing(monkeypatch):
    from app.engine import session_rotation
    from app.engine.prop_risk_sizing import PropRiskSizingResult

    seen_symbols: list[str] = []
    candles = _candles()
    cfg = session_rotation.SessionRotationConfig(symbol="MES")
    indicators = {"ema200": np.full(len(candles), 90.0), "atr": np.full(len(candles), 25.0)}

    def fake_sizer(sizing_input):
        seen_symbols.append(sizing_input.symbol)
        return PropRiskSizingResult(
            contracts=1,
            symbol=sizing_input.symbol,
            per_trade_risk_dollars=50,
            stop_ticks=50,
            dollars_at_risk_per_contract=25,
        )

    monkeypatch.setattr(session_rotation, "_compute_all_session_indicators", lambda config, candles: {"morning": indicators, "midday": indicators, "afternoon": indicators})
    monkeypatch.setitem(session_rotation.ENTRY_TRIGGERS, cfg.morning_trigger, lambda indicators, i: i == WARMUP)
    monkeypatch.setitem(session_rotation.CONFIRMATIONS, cfg.morning_filter, lambda indicators, i: True)
    monkeypatch.setattr(session_rotation, "calc_stop_price", lambda strategy, entry, indicators, i, short=False: entry - 50)
    monkeypatch.setattr(session_rotation, "calc_take_profit_price", lambda strategy, entry, stop, short=False: entry + 100)
    monkeypatch.setattr(session_rotation, "size_integer_micro_contracts", fake_sizer)

    result = session_rotation.run_session_backtest(cfg, candles, risk_pct=0.25, initial_capital=50_000)

    assert result.total_trades == 1
    assert seen_symbols == ["MES"]


def test_futures_position_pnl_uses_tick_value_not_raw_price_delta():
    assert futures_position_pnl("MYM", entry_price=35_000, exit_price=34_950, contracts=1, direction="long") == -25
    assert futures_position_pnl("MYM", entry_price=35_000, exit_price=35_100, contracts=2, direction="long") == 100
    assert futures_position_pnl("MYM", entry_price=35_000, exit_price=34_900, contracts=1, direction="short") == 50


def test_research_and_all_profiles_do_not_enforce_prop_allowlist():
    sizing = size_integer_micro_contracts(
        PropRiskSizingInput(
            symbol="MES",
            entry_price=5000,
            stop_price=4990,
            risk_level=0.25,
            prop_config=PropDoneRightConfig(official_mll_amount=2000),
            enforce_prop_profile=False,
        )
    )

    assert sizing.contracts >= 1
    assert sizing.skip_reason == ""
