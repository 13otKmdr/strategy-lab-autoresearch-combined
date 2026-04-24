"""
Weighted ranking engine for strategy evaluation.

Weights:
  30% profit factor
  20% net profit dollars
  15% total return %
  20% drawdown efficiency (return / max_dd)
  10% trade count robustness
   5% consistency across risk settings

Penalties:
  -40 pts  non-compliant
  -20 pts  too few trades (<20)
  -15 pts  unstable across risk levels (>50% score diff)
  -10 pts  outlier dependent (best trade > 40% of total profit)
"""
from __future__ import annotations

from app.models.backtest import BacktestResult
from app.models.ranking import RankedStrategy
from app.models.strategy import StrategyDefinition
from app.engine.metrics import analyze_strengths_weaknesses
from app.engine.prop_challenge_sim import simulate_prop_challenge


def rank_strategies(
    strategies: list[StrategyDefinition],
    results: dict[str, dict[float, BacktestResult]],
) -> list[RankedStrategy]:
    """
    Rank all strategies by composite score.

    Args:
        strategies: List of strategy definitions
        results: Dict mapping strategy_id -> {risk_pct -> BacktestResult}

    Returns:
        Sorted list of RankedStrategy (best first)
    """
    scored: list[RankedStrategy] = []

    for strat in strategies:
        sid = strat.strategy_id
        if sid not in results:
            continue
        r025 = results[sid].get(0.25)
        r050 = results[sid].get(0.5)
        if r025 is None or r050 is None:
            continue

        score = _compute_composite_score(r025, r050)

        # Run prop challenge path simulation on the primary risk level's trades
        challenge_result = simulate_prop_challenge(r025.trades)
        score = _apply_challenge_adjustment(score, challenge_result.outcome)

        strengths, weaknesses = analyze_strengths_weaknesses(r025, r050)

        overall_compliance = "compliant"
        if r025.compliance_status != "compliant" or r050.compliance_status != "compliant":
            overall_compliance = "non_compliant"

        scored.append(RankedStrategy(
            rank=0,  # assigned after sorting
            strategy_id=sid,
            strategy_name=strat.strategy_name,
            strategy_type=strat.strategy_type,
            market_type=strat.market_type,
            instrument=strat.intended_asset_classes[0] if strat.intended_asset_classes else "unknown",
            total_return_pct_025=r025.total_return_pct,
            net_profit_dollars_025=r025.net_profit_dollars,
            profit_factor_025=r025.profit_factor,
            max_drawdown_pct_025=r025.max_drawdown_pct,
            win_rate_025=r025.win_rate,
            total_trades_025=r025.total_trades,
            sharpe_ratio_025=r025.sharpe_ratio,
            compliance_status_025=r025.compliance_status,
            total_return_pct_050=r050.total_return_pct,
            net_profit_dollars_050=r050.net_profit_dollars,
            profit_factor_050=r050.profit_factor,
            max_drawdown_pct_050=r050.max_drawdown_pct,
            win_rate_050=r050.win_rate,
            total_trades_050=r050.total_trades,
            sharpe_ratio_050=r050.sharpe_ratio,
            compliance_status_050=r050.compliance_status,
            composite_score=score,
            overall_compliance=overall_compliance,
            challenge_outcome=challenge_result.outcome,
            challenge_total_profit=challenge_result.total_profit,
            challenge_days_traded=challenge_result.days_traded,
            challenge_best_day_profit=challenge_result.best_day_profit,
            challenge_consistency_passed=challenge_result.consistency_passed,
            challenge_mll_breached=challenge_result.mll_breached,
            challenge_trades_taken=challenge_result.trades_taken,
            challenge_trades_skipped=challenge_result.trades_skipped,
            strengths=strengths,
            weaknesses=weaknesses,
        ))

    scored.sort(key=lambda s: s.composite_score, reverse=True)
    for i, s in enumerate(scored):
        s.rank = i + 1

    return scored


def _compute_composite_score(r025: BacktestResult, r050: BacktestResult) -> float:
    """Compute weighted composite score from 0-100."""

    # Use the better of the two risk levels for each dimension
    pf = max(r025.profit_factor, r050.profit_factor)
    net_profit = max(r025.net_profit_dollars, r050.net_profit_dollars)
    total_return = max(r025.total_return_pct, r050.total_return_pct)
    avg_trades = (r025.total_trades + r050.total_trades) / 2

    # Drawdown efficiency: return / max_dd (higher is better)
    dd_eff_025 = r025.total_return_pct / r025.max_drawdown_pct if r025.max_drawdown_pct > 0 else 0
    dd_eff_050 = r050.total_return_pct / r050.max_drawdown_pct if r050.max_drawdown_pct > 0 else 0
    dd_efficiency = max(dd_eff_025, dd_eff_050)

    # Dimension scores (each 0-100)
    # 1. Profit factor: 1.0 -> 0, 3.0 -> 100 (capped)
    pf_capped = min(pf, 5.0) if pf != float("inf") else 5.0
    pf_score = max(0, min((pf_capped - 1.0) / 2.0, 1.0)) * 100

    # 2. Net profit dollars: $0 -> 0, $5000 -> 100 (on $50K account = 10%)
    profit_score = max(0, min(net_profit / 5000, 1.0)) * 100

    # 3. Total return %: 0% -> 0, 10% -> 100
    return_score = max(0, min(total_return / 0.10, 1.0)) * 100

    # 4. Drawdown efficiency: 0 -> 0, 5.0 -> 100 (5x return:dd ratio)
    dd_score = max(0, min(dd_efficiency / 5.0, 1.0)) * 100

    # 5. Trade count: <20 -> 0, 50 -> 50, 100+ -> 100, >300 penalty
    if avg_trades < 20:
        trade_score = 0
    elif avg_trades <= 100:
        trade_score = (avg_trades - 20) / 80 * 100
    elif avg_trades <= 300:
        trade_score = 100
    else:
        trade_score = max(50, 100 - (avg_trades - 300) / 10)

    # 6. Consistency: compare PF between risk levels (lower diff = better)
    avg_pf = (r025.profit_factor + r050.profit_factor) / 2
    if avg_pf > 0 and avg_pf != float("inf"):
        pf_diff_ratio = abs(r025.profit_factor - r050.profit_factor) / avg_pf
        consistency_score = max(0, (1 - pf_diff_ratio) * 100)
    else:
        consistency_score = 50

    # Weighted composite
    raw_score = (
        pf_score * 0.30 +
        profit_score * 0.20 +
        return_score * 0.15 +
        dd_score * 0.20 +
        trade_score * 0.10 +
        consistency_score * 0.05
    )

    # Apply penalties
    penalties = 0

    # Non-compliance penalty
    if r025.compliance_status != "compliant" or r050.compliance_status != "compliant":
        penalties += 40

    # Too few trades
    if avg_trades < 20:
        penalties += 20

    # Unstable across risk levels
    if avg_pf > 0 and avg_pf != float("inf"):
        if abs(r025.profit_factor - r050.profit_factor) / avg_pf > 0.50:
            penalties += 15

    # Outlier dependence
    for r in [r025, r050]:
        if r.net_profit_dollars > 0 and r.best_trade > 0.4 * r.net_profit_dollars:
            penalties += 10
            break

    # OOS degradation — likely overfit if OOS PF < 50% of IS PF
    for r in [r025, r050]:
        is_pf = r.profit_factor
        oos_pf = r.oos_profit_factor
        if is_pf > 1.0 and oos_pf > 0:
            if oos_pf < is_pf * 0.5:
                penalties += 20
                break
        elif is_pf > 1.0 and r.oos_total_trades == 0:
            penalties += 10  # no OOS trades = can't validate
            break

    # OOS negative Sharpe — strategy loses money on unseen data
    for r in [r025, r050]:
        if r.oos_sharpe_ratio < 0 and r.oos_total_trades >= 5:
            penalties += 15
            break

    return max(0, raw_score - penalties)


def _apply_challenge_adjustment(score: float, challenge_outcome: str) -> float:
    """Adjust composite score based on prop challenge simulation outcome.

    - ``pass``: +20 bonus — strategy demonstrably survives the Topstep 50K path
    - ``fail_mll``: −25 penalty — strategy blows the Maximum Loss Limit
    - ``fail_consistency``: −15 penalty — one-day concentration too high
    - ``timeout``: no adjustment — trade list ended without resolution
    """
    if challenge_outcome == "pass":
        return score + 20
    if challenge_outcome == "fail_mll":
        return max(0, score - 25)
    if challenge_outcome == "fail_consistency":
        return max(0, score - 15)
    # timeout — neutral
    return score
