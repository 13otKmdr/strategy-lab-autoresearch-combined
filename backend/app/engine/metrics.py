"""
Additional metric utilities beyond what backtester.py computes inline.
Strength/weakness analysis for the detail view.
"""
from __future__ import annotations

from app.models.backtest import BacktestResult


def analyze_strengths_weaknesses(
    result_025: BacktestResult,
    result_050: BacktestResult,
) -> tuple[list[str], list[str]]:
    """Analyze a strategy's test results and return (strengths, weaknesses)."""
    strengths: list[str] = []
    weaknesses: list[str] = []

    # Profit factor
    for r, label in [(result_025, "0.25%"), (result_050, "0.5%")]:
        if r.profit_factor >= 2.0:
            strengths.append(f"Strong profit factor of {r.profit_factor:.2f} at {label} risk")
        elif r.profit_factor < 1.2 and r.profit_factor > 0:
            weaknesses.append(f"Marginal profit factor of {r.profit_factor:.2f} at {label} risk")

    # Win rate
    avg_wr = (result_025.win_rate + result_050.win_rate) / 2
    if avg_wr >= 0.55:
        strengths.append(f"Above-average win rate ({avg_wr:.0%})")
    elif avg_wr < 0.40:
        weaknesses.append(f"Low win rate ({avg_wr:.0%}) — requires strong R:R to compensate")

    # Drawdown
    for r, label in [(result_025, "0.25%"), (result_050, "0.5%")]:
        if r.max_drawdown_pct <= 0.02:
            strengths.append(f"Tight drawdown control ({r.max_drawdown_pct:.1%}) at {label} risk")
        elif r.max_drawdown_pct > 0.04:
            weaknesses.append(f"Elevated drawdown ({r.max_drawdown_pct:.1%}) at {label} risk — exceeds futures limit")

    # Trade count
    avg_trades = (result_025.total_trades + result_050.total_trades) / 2
    if avg_trades >= 50:
        strengths.append(f"Good sample size ({avg_trades:.0f} avg trades)")
    elif avg_trades < 20:
        weaknesses.append(f"Low trade count ({avg_trades:.0f}) — results may not be statistically significant")

    # Sharpe
    avg_sharpe = (result_025.sharpe_ratio + result_050.sharpe_ratio) / 2
    if avg_sharpe >= 1.5:
        strengths.append(f"Strong risk-adjusted returns (Sharpe {avg_sharpe:.2f})")
    elif avg_sharpe < 0.5:
        weaknesses.append(f"Poor risk-adjusted returns (Sharpe {avg_sharpe:.2f})")

    # Consistency across risk levels
    if result_025.total_trades > 0 and result_050.total_trades > 0:
        pf_diff = abs(result_025.profit_factor - result_050.profit_factor)
        avg_pf = (result_025.profit_factor + result_050.profit_factor) / 2
        if avg_pf > 0 and pf_diff / avg_pf < 0.15:
            strengths.append("Consistent performance across both risk levels")
        elif avg_pf > 0 and pf_diff / avg_pf > 0.50:
            weaknesses.append("Unstable — large performance gap between 0.25% and 0.5% risk")

    # R-multiple
    avg_r = (result_025.avg_r_multiple + result_050.avg_r_multiple) / 2
    if avg_r >= 0.5:
        strengths.append(f"Excellent expected value per trade ({avg_r:.2f}R)")
    elif avg_r < 0.1:
        weaknesses.append(f"Low expected value per trade ({avg_r:.2f}R)")

    # Compliance
    if result_025.compliance_status == "compliant" and result_050.compliance_status == "compliant":
        strengths.append("Prop-firm compliant at both risk levels")
    else:
        weaknesses.append("Fails prop-firm drawdown compliance at one or both risk levels")

    # Best/worst trade outlier check
    for r, label in [(result_025, "0.25%"), (result_050, "0.5%")]:
        if r.net_profit_dollars > 0 and r.best_trade > 0.4 * r.net_profit_dollars:
            weaknesses.append(f"At {label} risk, best trade accounts for >{40}% of total profit — outlier risk")

    return strengths, weaknesses
