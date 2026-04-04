"""
Portfolio optimizer — selects the best combination of 2-3 strategies
that minimises drawdown while maximising risk-adjusted return.

Selection criteria:
  - Only strategies with composite_score > 10 and total_trades > 20
  - Combinations must be diversified (different strategy_types or instruments)
  - Ranked by lowest combined max drawdown, then highest combined Sharpe
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from app.models.backtest import BacktestResult
from app.models.ranking import RankedStrategy


@dataclass
class PortfolioResult:
    strategies: list[dict]              # [{strategy_id, name, instrument, weight}, ...]
    combined_return_pct: float
    combined_net_profit: float
    combined_max_dd_pct: float
    combined_max_dd_dollars: float
    combined_sharpe: float
    combined_profit_factor: float
    combined_trades: int
    diversification_score: float        # 0-1, how uncorrelated
    compliance_status: str
    correlation_matrix: list[list[float]]

    def to_dict(self) -> dict:
        return {
            "strategies": self.strategies,
            "combined_return_pct": round(self.combined_return_pct, 4),
            "combined_net_profit": round(self.combined_net_profit, 2),
            "combined_max_dd_pct": round(self.combined_max_dd_pct, 4),
            "combined_max_dd_dollars": round(self.combined_max_dd_dollars, 2),
            "combined_sharpe": round(self.combined_sharpe, 4),
            "combined_profit_factor": round(self.combined_profit_factor, 4),
            "combined_trades": self.combined_trades,
            "diversification_score": round(self.diversification_score, 4),
            "compliance_status": self.compliance_status,
            "correlation_matrix": [
                [round(v, 4) for v in row] for row in self.correlation_matrix
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equity_to_returns(curve: list[float]) -> np.ndarray:
    """Convert an equity curve to a series of daily returns."""
    arr = np.array(curve, dtype=float)
    returns = np.diff(arr) / arr[:-1]
    return returns


def _resample_curve(curve: list[float], target_len: int) -> np.ndarray:
    """Resample an equity curve to *target_len* points via linear interpolation."""
    arr = np.array(curve, dtype=float)
    if len(arr) == target_len:
        return arr
    x_old = np.linspace(0, 1, len(arr))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, arr)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_correlation(results: list[BacktestResult]) -> list[list[float]]:
    """
    Pairwise Pearson correlation of equity-curve returns.

    Returns an NxN matrix as a list of lists.
    """
    n = len(results)
    if n == 0:
        return []

    # Normalise all curves to the same length (shortest)
    min_len = min(len(r.equity_curve) for r in results)
    if min_len < 2:
        return [[1.0] * n for _ in range(n)]

    returns_list = []
    for r in results:
        resampled = _resample_curve(r.equity_curve, min_len)
        returns_list.append(_equity_to_returns(resampled.tolist()))

    matrix: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i == j:
                row.append(1.0)
            else:
                corr = float(np.corrcoef(returns_list[i], returns_list[j])[0, 1])
                if math.isnan(corr):
                    corr = 0.0
                row.append(corr)
        matrix.append(row)

    return matrix


def combine_equity_curves(
    results: list[BacktestResult],
    weights: list[float],
) -> list[float]:
    """
    Weighted combination of equity curves, normalised to the same length.

    Each curve is first normalised to percentage returns from its starting
    value, combined with the given weights, then scaled back to an absolute
    equity starting at the average initial capital.
    """
    if not results:
        return []

    target_len = min(len(r.equity_curve) for r in results)
    if target_len < 2:
        return []

    combined = np.zeros(target_len, dtype=float)
    avg_capital = np.mean([r.equity_curve[0] for r in results])

    for r, w in zip(results, weights):
        resampled = _resample_curve(r.equity_curve, target_len)
        # Normalise to fraction-of-start
        normed = resampled / resampled[0]
        combined += normed * w

    # Scale to dollar equity
    return (combined * avg_capital).tolist()


def optimize_portfolio(
    candidates: list[tuple[RankedStrategy, BacktestResult]],
    max_strategies: int = 3,
) -> PortfolioResult | None:
    """
    Find the best 2-3 strategy portfolio from ranked candidates.

    Returns None if fewer than 2 eligible candidates exist.
    """
    # --- Filter eligible candidates -----------------------------------------
    eligible = [
        (rs, bt)
        for rs, bt in candidates
        if rs.composite_score > 10 and bt.total_trades > 20
    ]
    if len(eligible) < 2:
        return None

    # Pre-filter to top 20 by composite score for tractability
    eligible.sort(key=lambda x: x[0].composite_score, reverse=True)
    eligible = eligible[:20]

    # --- Evaluate all 2- and 3-strategy combinations ------------------------
    best_score: tuple[float, float] | None = None   # (max_dd, -sharpe)
    best_portfolio: PortfolioResult | None = None

    for size in range(2, min(max_strategies, len(eligible)) + 1):
        for combo in itertools.combinations(range(len(eligible)), size):
            items = [eligible[i] for i in combo]
            ranked = [it[0] for it in items]
            bt_results = [it[1] for it in items]

            # --- Diversification check: different strategy_types OR instruments
            types = {rs.strategy_type for rs in ranked}
            instruments = {rs.instrument for rs in ranked}
            if len(types) == 1 and len(instruments) == 1:
                continue  # not diversified enough

            # --- Equal weights
            n = len(bt_results)
            weights = [1.0 / n] * n

            # --- Combined equity curve
            combined_curve = combine_equity_curves(bt_results, weights)
            if len(combined_curve) < 2:
                continue

            combined_arr = np.array(combined_curve)
            start_equity = combined_arr[0]

            # --- Combined metrics
            combined_return_pct = (combined_arr[-1] - start_equity) / start_equity
            combined_net_profit = combined_arr[-1] - start_equity

            # Max drawdown
            running_max = np.maximum.accumulate(combined_arr)
            drawdowns = (running_max - combined_arr) / running_max
            max_dd_pct = float(np.max(drawdowns))
            max_dd_dollars = float(np.max(running_max - combined_arr))

            # Sharpe from combined returns
            combined_returns = np.diff(combined_arr) / combined_arr[:-1]
            mean_ret = float(np.mean(combined_returns))
            std_ret = float(np.std(combined_returns, ddof=1)) if len(combined_returns) > 1 else 1.0
            combined_sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0

            # Combined profit factor (sum of gross profits / sum of gross losses)
            total_gross_profit = sum(bt.gross_profit * w for bt, w in zip(bt_results, weights))
            total_gross_loss = sum(abs(bt.gross_loss) * w for bt, w in zip(bt_results, weights))
            combined_pf = total_gross_profit / total_gross_loss if total_gross_loss > 0 else 0.0

            # Total trades
            combined_trades = sum(bt.total_trades for bt in bt_results)

            # Correlation & diversification score
            corr_matrix = compute_correlation(bt_results)
            avg_abs_corr = _avg_off_diagonal(corr_matrix)
            diversification_score = max(0.0, 1.0 - avg_abs_corr)

            # Compliance
            all_compliant = all(bt.compliance_status == "compliant" for bt in bt_results)
            compliance = "compliant" if all_compliant else "non_compliant"

            # --- Rank: lower DD first, then higher Sharpe
            score = (max_dd_pct, -combined_sharpe)
            if best_score is None or score < best_score:
                best_score = score
                best_portfolio = PortfolioResult(
                    strategies=[
                        {
                            "strategy_id": rs.strategy_id,
                            "name": rs.strategy_name,
                            "instrument": rs.instrument,
                            "weight": round(w, 4),
                        }
                        for rs, w in zip(ranked, weights)
                    ],
                    combined_return_pct=float(combined_return_pct),
                    combined_net_profit=float(combined_net_profit),
                    combined_max_dd_pct=float(max_dd_pct),
                    combined_max_dd_dollars=float(max_dd_dollars),
                    combined_sharpe=float(combined_sharpe),
                    combined_profit_factor=float(combined_pf),
                    combined_trades=combined_trades,
                    diversification_score=diversification_score,
                    compliance_status=compliance,
                    correlation_matrix=corr_matrix,
                )

    return best_portfolio


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _avg_off_diagonal(matrix: list[list[float]]) -> float:
    """Average absolute value of off-diagonal elements in a correlation matrix."""
    n = len(matrix)
    if n < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(n):
            if i != j:
                total += abs(matrix[i][j])
                count += 1
    return total / count if count > 0 else 0.0
