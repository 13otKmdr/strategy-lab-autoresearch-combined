"""Monte Carlo challenge pass probability engine.

Resamples historical trades (with replacement) and runs the full
``simulate_prop_challenge()`` on each path — accounting for MLL trailing,
consistency rule, DRB lockouts, Power of Quitting, and max trades/day.

Returns pass/fail probability breakdowns that feed into the ranking score.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.prop_challenge_sim import simulate_prop_challenge, PropChallengeResult
from app.models.backtest import Trade


@dataclass(frozen=True)
class MCChallengeResult:
    """Monte Carlo challenge simulation aggregate result."""
    pass_rate: float
    mll_breach_rate: float
    consistency_fail_rate: float
    timeout_rate: float
    avg_days_to_pass: float
    avg_profit_if_pass: float
    n_sims: int


def mc_challenge_pass_rate(
    trades: list[Trade],
    n_sims: int = 200,
    seed: int = 42,
) -> MCChallengeResult:
    """Run Monte Carlo simulations of the Topstep 50K challenge path.

    For each simulation:
    1. Resample the trade list (with replacement) to build a randomised path
    2. Run ``simulate_prop_challenge()`` on that path (full MLL, consistency, DRB)
    3. Aggregate outcomes into pass/fail/timeout rates

    Args:
        trades: List of closed backtest trades to resample.
        n_sims: Number of Monte Carlo paths (default 200 for speed).
        seed: Random seed for reproducibility.

    Returns:
        MCChallengeResult with pass_rate, mll_breach_rate, etc.
    """
    if len(trades) < 5:
        return MCChallengeResult(
            pass_rate=0.0, mll_breach_rate=1.0, consistency_fail_rate=0.0,
            timeout_rate=0.0, avg_days_to_pass=0.0, avg_profit_if_pass=0.0,
            n_sims=n_sims,
        )

    rng = np.random.default_rng(seed=seed)
    indices = np.arange(len(trades))

    passes = 0
    mll_breaches = 0
    consistency_fails = 0
    timeouts = 0
    days_to_pass: list[int] = []
    profit_if_pass: list[float] = []

    for _ in range(n_sims):
        # Resample trade indices (same length as original, with replacement)
        sampled_idx = rng.choice(indices, size=len(trades), replace=True)
        sampled_trades = [trades[i] for i in sampled_idx]

        result: PropChallengeResult = simulate_prop_challenge(sampled_trades)

        if result.outcome == "pass":
            passes += 1
            days_to_pass.append(result.days_traded)
            profit_if_pass.append(result.total_profit)
        elif result.outcome == "fail_mll":
            mll_breaches += 1
        elif result.outcome == "fail_consistency":
            consistency_fails += 1
        else:
            timeouts += 1

    return MCChallengeResult(
        pass_rate=passes / n_sims,
        mll_breach_rate=mll_breaches / n_sims,
        consistency_fail_rate=consistency_fails / n_sims,
        timeout_rate=timeouts / n_sims,
        avg_days_to_pass=float(np.mean(days_to_pass)) if days_to_pass else 0.0,
        avg_profit_if_pass=float(np.mean(profit_if_pass)) if profit_if_pass else 0.0,
        n_sims=n_sims,
    )
