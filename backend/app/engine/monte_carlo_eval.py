"""
Monte Carlo Prop Firm Evaluation Simulator.

Resamples historical trades (with replacement) to run thousands of simulated
evaluation attempts, estimating pass/fail probabilities and risk metrics for
prop firm challenges like Topstep, Apex, etc.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.models.backtest import BacktestResult


@dataclass
class PropFirmConfig:
    account_size: float = 50_000
    profit_target: float = 3_000
    trailing_dd_limit: float = 2_000
    daily_loss_limit: float = 1_000
    min_trading_days: int = 5
    max_eval_days: int = 30
    trades_per_day: float = 3.0


@dataclass
class EvalSimResult:
    pass_rate: float
    blow_rate: float
    daily_loss_blow_rate: float
    avg_days_to_pass: float
    avg_profit_if_pass: float
    p95_max_drawdown: float
    p50_final_pnl: float
    n_sims: int


# ── Presets ──────────────────────────────────────────────────────────────────

TOPSTEP_50K = PropFirmConfig(
    account_size=50_000,
    profit_target=3_000,
    trailing_dd_limit=2_000,
    daily_loss_limit=1_000,
    min_trading_days=5,
    max_eval_days=30,
)

TOPSTEP_100K = PropFirmConfig(
    account_size=100_000,
    profit_target=6_000,
    trailing_dd_limit=3_000,
    daily_loss_limit=2_000,
    min_trading_days=5,
    max_eval_days=30,
)

APEX_50K = PropFirmConfig(
    account_size=50_000,
    profit_target=3_000,
    trailing_dd_limit=2_500,
    daily_loss_limit=1_500,
    min_trading_days=7,
    max_eval_days=30,
)


# ── Core simulation ─────────────────────────────────────────────────────────

def simulate_eval(
    backtest_result: BacktestResult,
    config: PropFirmConfig,
    n_sims: int = 1_000,
) -> EvalSimResult:
    """
    Run Monte Carlo simulations of a prop firm evaluation.

    Resamples trades with replacement from the backtest, groups them into
    simulated trading days, and checks pass/fail conditions on each path.
    """
    pnls = np.array([t.pnl for t in backtest_result.trades], dtype=float)

    if len(pnls) < 5:
        return EvalSimResult(
            pass_rate=0.0,
            blow_rate=1.0,
            daily_loss_blow_rate=0.0,
            avg_days_to_pass=float(config.max_eval_days),
            avg_profit_if_pass=0.0,
            p95_max_drawdown=config.trailing_dd_limit,
            p50_final_pnl=0.0,
            n_sims=n_sims,
        )

    rng = np.random.default_rng(seed=42)
    trades_per_day = max(1, int(round(config.trades_per_day)))
    total_trades = config.max_eval_days * trades_per_day

    passes = 0
    blows = 0
    daily_loss_blows = 0
    days_to_pass: list[float] = []
    profit_if_pass: list[float] = []
    max_drawdowns: list[float] = []
    final_pnls: list[float] = []

    for _ in range(n_sims):
        sample = rng.choice(pnls, size=total_trades, replace=True)

        running_pnl = 0.0
        peak_pnl = 0.0
        outcome = "timeout"  # "pass", "blown_trailing", "blown_daily", "timeout"
        outcome_day = config.max_eval_days
        sim_max_dd = 0.0

        for day in range(config.max_eval_days):
            start = day * trades_per_day
            end = start + trades_per_day
            day_pnl = 0.0

            for t in range(start, end):
                running_pnl += sample[t]
                day_pnl += sample[t]

                if running_pnl > peak_pnl:
                    peak_pnl = running_pnl

                trailing_dd = peak_pnl - running_pnl
                if trailing_dd > sim_max_dd:
                    sim_max_dd = trailing_dd

                # Check trailing drawdown limit
                if trailing_dd >= config.trailing_dd_limit:
                    outcome = "blown_trailing"
                    outcome_day = day + 1
                    break

            if outcome == "blown_trailing":
                break

            # Check daily loss limit
            if day_pnl <= -config.daily_loss_limit:
                outcome = "blown_daily"
                outcome_day = day + 1
                break

            # Check pass condition (must meet min trading days)
            if running_pnl >= config.profit_target and (day + 1) >= config.min_trading_days:
                outcome = "pass"
                outcome_day = day + 1
                break

        max_drawdowns.append(sim_max_dd)
        final_pnls.append(running_pnl)

        if outcome == "pass":
            passes += 1
            days_to_pass.append(outcome_day)
            profit_if_pass.append(running_pnl)
        elif outcome == "blown_trailing":
            blows += 1
        elif outcome == "blown_daily":
            daily_loss_blows += 1
            blows += 1

    max_drawdowns.sort()
    final_pnls.sort()

    p95_idx = min(int(n_sims * 0.95), n_sims - 1)
    p50_idx = n_sims // 2

    return EvalSimResult(
        pass_rate=passes / n_sims,
        blow_rate=blows / n_sims,
        daily_loss_blow_rate=daily_loss_blows / n_sims,
        avg_days_to_pass=float(np.mean(days_to_pass)) if days_to_pass else float(config.max_eval_days),
        avg_profit_if_pass=float(np.mean(profit_if_pass)) if profit_if_pass else 0.0,
        p95_max_drawdown=max_drawdowns[p95_idx],
        p50_final_pnl=final_pnls[p50_idx],
        n_sims=n_sims,
    )


# ── Funded phase simulation ─────────────────────────────────────────────────

def funded_phase_sim(
    backtest_result: BacktestResult,
    config: PropFirmConfig | None = None,
    monthly_days: int = 22,
    n_sims: int = 500,
) -> dict:
    """
    Simulate monthly income from a funded account.

    Estimates monthly P&L distribution and the probability of losing the
    funded account in any given month (hitting the trailing DD limit).
    """
    if config is None:
        config = TOPSTEP_50K

    pnls = np.array([t.pnl for t in backtest_result.trades], dtype=float)

    if len(pnls) < 5:
        return {
            "avg_monthly_income": 0.0,
            "p25_monthly_income": 0.0,
            "p50_monthly_income": 0.0,
            "p75_monthly_income": 0.0,
            "monthly_blow_rate": 1.0,
            "expected_account_lifetime_months": 0.0,
        }

    rng = np.random.default_rng(seed=123)
    trades_per_day = max(1, int(round(config.trades_per_day)))
    total_trades = monthly_days * trades_per_day

    monthly_incomes: list[float] = []
    blow_count = 0

    for _ in range(n_sims):
        sample = rng.choice(pnls, size=total_trades, replace=True)

        running_pnl = 0.0
        peak_pnl = 0.0
        blown = False

        for day in range(monthly_days):
            start = day * trades_per_day
            end = start + trades_per_day
            day_pnl = 0.0

            for t in range(start, end):
                running_pnl += sample[t]
                day_pnl += sample[t]

                if running_pnl > peak_pnl:
                    peak_pnl = running_pnl

                trailing_dd = peak_pnl - running_pnl
                if trailing_dd >= config.trailing_dd_limit:
                    blown = True
                    break

            if blown:
                break

            if day_pnl <= -config.daily_loss_limit:
                blown = True
                break

        if blown:
            blow_count += 1
            monthly_incomes.append(0.0)
        else:
            monthly_incomes.append(running_pnl)

    monthly_incomes.sort()
    monthly_blow_rate = blow_count / n_sims

    return {
        "avg_monthly_income": float(np.mean(monthly_incomes)),
        "p25_monthly_income": float(monthly_incomes[int(n_sims * 0.25)]),
        "p50_monthly_income": float(monthly_incomes[n_sims // 2]),
        "p75_monthly_income": float(monthly_incomes[int(n_sims * 0.75)]),
        "monthly_blow_rate": monthly_blow_rate,
        "expected_account_lifetime_months": (1.0 / monthly_blow_rate) if monthly_blow_rate > 0 else float("inf"),
    }
