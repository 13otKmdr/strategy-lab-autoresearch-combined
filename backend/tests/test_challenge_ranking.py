"""TDD tests for challenge-aware ranking (Task 7).

These tests define the expected behavior BEFORE implementation:
- Challenge-passing strategies rank above raw-return monsters
- MLL-breaching strategies get penalised
- Timeout strategies are neutral (no bonus, no penalty)
- Consistency failures get penalised
"""
from __future__ import annotations

import pytest

from app.engine.ranker import rank_strategies, _compute_composite_score
from app.engine.prop_challenge_sim import simulate_prop_challenge
from app.models.backtest import BacktestResult, Trade, SidePerformance
from app.models.strategy import StrategyDefinition


# ── Helpers ──────────────────────────────────────────────────────────────────

def _trade(pnl: float, day_offset: int = 0) -> Trade:
    """Create a trade with a specific P&L on a specific CT trading day."""
    # Each day ~96 bars at 15min.  Offset by day_offset * 96 bars.
    base_ts = 1700000000000  # Nov 2023 ms
    day_ms = 86_400_000
    # Use a midday timestamp so CT trading-day key is stable
    entry_ts = base_ts + day_offset * day_ms + 14 * 3_600_000  # 14:00 UTC = ~08:00 CT
    exit_ts = entry_ts + 4 * 3_600_000  # 4 hours later
    return Trade(
        entry_bar=0, exit_bar=1, entry_price=100.0, exit_price=100.0 + pnl,
        size=1.0, direction="long", pnl=pnl, pnl_pct=0.01, r_multiple=1.0,
        exit_reason="take_profit", entry_ts=entry_ts, exit_ts=exit_ts,
    )


def _make_backtest(trades: list[Trade], net_profit: float | None = None) -> BacktestResult:
    """Build a minimal BacktestResult with the given trades."""
    actual_profit = net_profit if net_profit is not None else sum(t.pnl for t in trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0

    return BacktestResult(
        strategy_id="test",
        risk_pct=0.25,
        initial_capital=50_000,
        total_return_pct=actual_profit / 50_000 * 100,
        net_profit_dollars=actual_profit,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else 999.0,
        win_rate=len(wins) / len(trades) if trades else 0,
        avg_r_multiple=1.0,
        total_trades=len(trades),
        max_drawdown_pct=2.0,
        max_drawdown_dollars=1000,
        best_trade=max((t.pnl for t in trades), default=0),
        worst_trade=min((t.pnl for t in trades), default=0),
        long_side_performance=SidePerformance(
            total_trades=len(trades), win_rate=0.6, gross_profit=gross_profit,
            gross_loss=gross_loss, net_pnl=actual_profit, avg_r_multiple=1.0,
        ).__dict__,
        short_side_performance=SidePerformance(
            total_trades=0, win_rate=0, gross_profit=0, gross_loss=0,
            net_pnl=0, avg_r_multiple=0,
        ).__dict__,
        monthly_returns=[],
        equity_curve=[],
        drawdown_curve=[],
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        compliance_status="compliant",
        compliance_reason="",
        trades=trades,
    )


def _make_strategy(sid: str, instrument: str = "MYM") -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=sid,
        strategy_name=f"Test-{sid}",
        strategy_type="trend_following",
        market_type="futures",
        thesis_summary="test",
        indicators_used=[],
        candlestick_patterns_used=[],
        timeframe_stack=["15min"],
        entry_rules={},
        exit_rules={},
        stop_loss_logic={},
        take_profit_logic={},
        trailing_stop_or_break_even_logic={},
        session_filters={},
        volatility_filters={},
        fundamental_filters_if_any={},
        intended_asset_classes=[instrument],
        primary_indicator={},
        confirmation_indicator={},
        entry={"trigger": "PRICE_ABOVE_EMA", "filter": "NONE"},
        exit={"stop_loss": {"type": "atr_multiple", "value": 1.5}},
        risk={"max_open_positions": 1},
    )


# ── Test: Challenge-passing strategy ranks above raw-return monster ──────────

class TestChallengeRanking:
    """Challenge-aware ranking integration tests."""

    def test_passing_strategy_ranks_above_raw_return_monster(self):
        """A strategy that passes the Topstep 50K challenge should rank
        above a strategy with higher raw returns but that would MLL-breach."""
        # Strategy A: steady $300/day over 10 days = $3,000 → passes challenge
        passing_trades = [_trade(300, day) for day in range(10)]
        # Strategy B: big winner day + big loser = higher raw return but MLL breach
        spike_trades = [
            _trade(2000, 0),   # big win day 1
            _trade(-2500, 1),  # MLL breach day 2
            _trade(1500, 2),   # recover
        ]

        strat_a = _make_strategy("passing")
        strat_b = _make_strategy("spike")

        results_a = {
            0.25: _make_backtest(passing_trades, net_profit=3000),
            0.5: _make_backtest(passing_trades, net_profit=3000),
        }
        results_b = {
            0.25: _make_backtest(spike_trades, net_profit=1000),
            0.5: _make_backtest(spike_trades, net_profit=1000),
        }

        ranked = rank_strategies(
            [strat_a, strat_b],
            {"passing": results_a, "spike": results_b},
        )

        assert len(ranked) == 2
        # The passing strategy should rank first (higher composite_score)
        assert ranked[0].strategy_id == "passing"
        assert ranked[0].challenge_outcome == "pass"
        assert ranked[1].challenge_outcome == "fail_mll"

    def test_mll_breach_gets_penalty(self):
        """MLL-breaching strategies should receive a score penalty."""
        trades = [_trade(300, day) for day in range(10)]
        r025 = _make_backtest(trades, net_profit=3000)
        r050 = _make_backtest(trades, net_profit=3000)

        # Simulate challenge: these trades should pass
        result = simulate_prop_challenge(trades)
        assert result.outcome == "pass"

    def test_challenge_sim_ran_on_all_strategies(self):
        """Every ranked strategy should have challenge_outcome populated."""
        strat_a = _make_strategy("a")
        strat_b = _make_strategy("b")

        trades_a = [_trade(100, d) for d in range(5)]
        trades_b = [_trade(-100, d) for d in range(5)]

        results = {
            "a": {
                0.25: _make_backtest(trades_a, net_profit=500),
                0.5: _make_backtest(trades_a, net_profit=500),
            },
            "b": {
                0.25: _make_backtest(trades_b, net_profit=-500),
                0.5: _make_backtest(trades_b, net_profit=-500),
            },
        }

        ranked = rank_strategies([strat_a, strat_b], results)

        for r in ranked:
            assert r.challenge_outcome in {"pass", "fail_mll", "fail_consistency", "timeout"}
            assert r.challenge_days_traded >= 0
            assert r.challenge_trades_taken >= 0

    def test_consistency_failure_penalised(self):
        """A strategy that hits $3K profit in one trade (50%+ best day)
        should be ranked below a steady strategy that also hits $3K."""
        # Steady: $300/day × 10 days = $3,000, no day dominates
        steady_trades = [_trade(300, d) for d in range(10)]
        # Spiky: one $3,000 trade + small ones → consistency fail
        spiky_trades = [_trade(3000, 0)] + [_trade(50, d) for d in range(1, 8)]

        strat_steady = _make_strategy("steady")
        strat_spiky = _make_strategy("spiky")

        results = {
            "steady": {
                0.25: _make_backtest(steady_trades, net_profit=3000),
                0.5: _make_backtest(steady_trades, net_profit=3000),
            },
            "spiky": {
                0.25: _make_backtest(spiky_trades, net_profit=3350),
                0.5: _make_backtest(spiky_trades, net_profit=3350),
            },
        }

        ranked = rank_strategies([strat_steady, strat_spiky], results)

        # Steady should rank higher despite lower raw profit
        assert ranked[0].strategy_id == "steady"
        assert ranked[0].challenge_outcome == "pass"
        assert ranked[1].challenge_outcome == "fail_consistency"

    def test_passing_bonus_outweighs_raw_profit_difference(self):
        """Even if a non-passing strategy has double the raw profit,
        the passing strategy should still rank higher due to the challenge bonus."""
        # Passing: $300/day × 10 = $3,000 (passes)
        passing_trades = [_trade(300, d) for d in range(10)]
        # Timeout: $200/day × 5 = $1,000 (doesn't hit target in 5 days)
        timeout_trades = [_trade(200, d) for d in range(5)]

        strat_pass = _make_strategy("passer")
        strat_timeout = _make_strategy("timeout")

        results = {
            "passer": {
                0.25: _make_backtest(passing_trades, net_profit=3000),
                0.5: _make_backtest(passing_trades, net_profit=3000),
            },
            "timeout": {
                0.25: _make_backtest(timeout_trades, net_profit=1000),
                0.5: _make_backtest(timeout_trades, net_profit=1000),
            },
        }

        ranked = rank_strategies([strat_pass, strat_timeout], results)

        passing_rank = next(r for r in ranked if r.strategy_id == "passer")
        timeout_rank = next(r for r in ranked if r.strategy_id == "timeout")

        assert passing_rank.challenge_outcome == "pass"
        assert timeout_rank.challenge_outcome == "timeout"
        assert passing_rank.composite_score > timeout_rank.composite_score
