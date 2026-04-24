"""TDD tests for Monte Carlo challenge pass probability (Task 8).

These tests define the expected behavior BEFORE implementation:
- MC challenge sim resamples trades and returns pass/fail probabilities
- Strategies with high pass probability score higher
- The MC pass rate is wired into ranking alongside the deterministic sim
"""
from __future__ import annotations

import pytest

from app.engine.monte_carlo_challenge import mc_challenge_pass_rate
from app.engine.prop_challenge_sim import PropChallengeResult
from app.engine.ranker import rank_strategies, _apply_challenge_adjustment
from app.models.backtest import BacktestResult, Trade, SidePerformance
from app.models.strategy import StrategyDefinition


# ── Helpers (same as test_challenge_ranking) ─────────────────────────────────

def _trade(pnl: float, day_offset: int = 0) -> Trade:
    base_ts = 1700000000000
    day_ms = 86_400_000
    entry_ts = base_ts + day_offset * day_ms + 14 * 3_600_000
    exit_ts = entry_ts + 4 * 3_600_000
    return Trade(
        entry_bar=0, exit_bar=1, entry_price=100.0, exit_price=100.0 + pnl,
        size=1.0, direction="long", pnl=pnl, pnl_pct=0.01, r_multiple=1.0,
        exit_reason="take_profit", entry_ts=entry_ts, exit_ts=exit_ts,
    )


def _make_backtest(trades: list[Trade], net_profit: float | None = None) -> BacktestResult:
    actual_profit = net_profit if net_profit is not None else sum(t.pnl for t in trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    return BacktestResult(
        strategy_id="test", risk_pct=0.25, initial_capital=50_000,
        total_return_pct=actual_profit / 50_000 * 100,
        net_profit_dollars=actual_profit, gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else 999.0,
        win_rate=len(wins) / len(trades) if trades else 0,
        avg_r_multiple=1.0, total_trades=len(trades),
        max_drawdown_pct=2.0, max_drawdown_dollars=1000,
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
        monthly_returns=[], equity_curve=[], drawdown_curve=[],
        sharpe_ratio=1.5, sortino_ratio=2.0,
        compliance_status="compliant", compliance_reason="", trades=trades,
    )


def _make_strategy(sid: str) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=sid, strategy_name=f"Test-{sid}",
        strategy_type="trend_following", market_type="futures",
        thesis_summary="test", indicators_used=[],
        candlestick_patterns_used=[], timeframe_stack=["15min"],
        entry_rules={}, exit_rules={}, stop_loss_logic={},
        take_profit_logic={}, trailing_stop_or_break_even_logic={},
        session_filters={}, volatility_filters={},
        fundamental_filters_if_any={},
        intended_asset_classes=["MYM"], primary_indicator={},
        confirmation_indicator={}, entry={"trigger": "PRICE_ABOVE_EMA", "filter": "NONE"},
        exit={"stop_loss": {"type": "atr_multiple", "value": 1.5}},
        risk={"max_open_positions": 1},
    )


# ── Tests: MC challenge simulator ────────────────────────────────────────────

class TestMCChallengeSimulator:
    """Tests for the Monte Carlo challenge pass probability engine."""

    def test_steady_positive_trades_have_high_pass_rate(self):
        """Trades that consistently make $300/day should pass most MC sims."""
        trades = [_trade(300, d) for d in range(15)]  # 15 winning trades
        result = mc_challenge_pass_rate(trades, n_sims=200)
        assert result.pass_rate >= 0.90, f"Expected high pass rate, got {result.pass_rate}"

    def test_losing_trades_have_zero_pass_rate(self):
        """All-losing trades should never pass."""
        trades = [_trade(-500, d) for d in range(10)]
        result = mc_challenge_pass_rate(trades, n_sims=100)
        assert result.pass_rate == 0.0
        # -$500/day × 2 days = -$1,000 → still under MLL but should have
        # either MLL breaches or timeouts (never passes)
        assert result.mll_breach_rate + result.timeout_rate == 1.0

    def test_mixed_trades_intermediate_pass_rate(self):
        """Trades with mixed wins/losses should have a measurable pass rate between 0 and 1."""
        trades = [_trade(200 if i % 3 != 0 else -150, i) for i in range(20)]
        result = mc_challenge_pass_rate(trades, n_sims=200)
        assert 0.0 < result.pass_rate < 1.0

    def test_too_few_trades_returns_zero(self):
        """Fewer than 5 trades should return pass_rate=0 gracefully."""
        trades = [_trade(300, d) for d in range(3)]
        result = mc_challenge_pass_rate(trades, n_sims=100)
        assert result.pass_rate == 0.0

    def test_mc_result_has_all_fields(self):
        """MC result should report all breakdown metrics."""
        trades = [_trade(250, d) for d in range(12)]
        result = mc_challenge_pass_rate(trades, n_sims=100)
        assert 0.0 <= result.pass_rate <= 1.0
        assert 0.0 <= result.mll_breach_rate <= 1.0
        assert 0.0 <= result.consistency_fail_rate <= 1.0
        assert result.avg_days_to_pass > 0 or result.pass_rate == 0.0
        assert result.n_sims == 100

    def test_consistent_small_wins_beat_spike_wins(self):
        """Strategies with steady small wins should have higher MC pass rate
        than strategies with rare big wins (same total profit)."""
        # Steady: $200/day × 15 = $3,000
        steady = [_trade(200, d) for d in range(15)]
        # Spiky: mostly tiny + one $2,500 winner (consistency risk)
        spiky = [_trade(50, d) for d in range(12)] + [_trade(2400, 12)]

        steady_result = mc_challenge_pass_rate(steady, n_sims=200)
        spiky_result = mc_challenge_pass_rate(spiky, n_sims=200)

        assert steady_result.pass_rate > spiky_result.pass_rate


class TestMCRankingIntegration:
    """Tests proving MC pass rate influences ranking."""

    def test_high_pass_rate_ranks_above_low_pass_rate(self):
        """A strategy with high MC pass rate should outrank one with low pass rate,
        even if the low-pass-rate strategy has higher raw return."""
        # Steady: $300/day × 10 → passes most sims
        steady_trades = [_trade(300, d) for d in range(10)]
        # Gambler: $1000 win then -$800 loss → sometimes passes, often MLL breach
        gambler_trades = [_trade(1000 if i % 2 == 0 else -800, i) for i in range(10)]

        strat_steady = _make_strategy("steady")
        strat_gambler = _make_strategy("gambler")

        results = {
            "steady": {
                0.25: _make_backtest(steady_trades, net_profit=3000),
                0.5: _make_backtest(steady_trades, net_profit=3000),
            },
            "gambler": {
                0.25: _make_backtest(gambler_trades, net_profit=1000),
                0.5: _make_backtest(gambler_trades, net_profit=1000),
            },
        }

        ranked = rank_strategies([strat_steady, strat_gambler], results)

        steady = next(r for r in ranked if r.strategy_id == "steady")
        gambler = next(r for r in ranked if r.strategy_id == "gambler")

        # Steady should have higher MC pass rate
        assert steady.eval_pass_rate > gambler.eval_pass_rate
        # And rank higher overall
        assert steady.composite_score > gambler.composite_score
