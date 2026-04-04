"""
Strategy API endpoints.
GET /api/strategies/:id — full strategy detail + both backtest results
GET /api/strategies/:id/equity — equity curve data for charting
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.data import storage
from app.engine.metrics import analyze_strengths_weaknesses
from app.models.backtest import BacktestResult

router = APIRouter()


@router.get("/strategies/{strategy_id}")
async def get_strategy_detail(strategy_id: str):
    """Get full strategy detail with both backtest results."""
    storage.init_db()

    definition = storage.get_strategy(strategy_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    results = storage.get_backtest_results(strategy_id)
    result_025 = next((r for r in results if abs(r.get("risk_pct", 0) - 0.25) < 0.01), None)
    result_050 = next((r for r in results if abs(r.get("risk_pct", 0) - 0.5) < 0.01), None)

    equity_data = storage.get_equity_curves(strategy_id)

    # Compute strengths/weaknesses if we have both results
    strengths, weaknesses = [], []
    if result_025 and result_050:
        # Build minimal BacktestResult objects for the analysis function
        # The stored results are dicts from to_dict() so they have the fields we need
        try:
            r025 = _dict_to_backtest_result(result_025)
            r050 = _dict_to_backtest_result(result_050)
            strengths, weaknesses = analyze_strengths_weaknesses(r025, r050)
        except Exception:
            pass

    return {
        "strategy": definition,
        "result_025": result_025,
        "result_050": result_050,
        "equity_data": {
            "equity_curve_025": equity_data.get("0.25", {}).get("equity_curve", []),
            "equity_curve_050": equity_data.get("0.50", {}).get("equity_curve", []),
            "drawdown_curve_025": equity_data.get("0.25", {}).get("drawdown_curve", []),
            "drawdown_curve_050": equity_data.get("0.50", {}).get("drawdown_curve", []),
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


@router.get("/strategies/{strategy_id}/equity")
async def get_strategy_equity(strategy_id: str):
    """Get equity curve and drawdown curve data for charting."""
    storage.init_db()
    data = storage.get_equity_curves(strategy_id)
    if not data:
        raise HTTPException(status_code=404, detail="No equity data found")
    return data


def _dict_to_backtest_result(d: dict) -> BacktestResult:
    """Convert a result dict back to a BacktestResult for analysis."""
    return BacktestResult(
        strategy_id=d.get("strategy_id", ""),
        risk_pct=d.get("risk_pct", 0),
        initial_capital=d.get("initial_capital", 50000),
        total_return_pct=d.get("total_return_pct", 0),
        net_profit_dollars=d.get("net_profit_dollars", 0),
        gross_profit=d.get("gross_profit", 0),
        gross_loss=d.get("gross_loss", 0),
        profit_factor=d.get("profit_factor", 0),
        win_rate=d.get("win_rate", 0),
        avg_r_multiple=d.get("avg_r_multiple", 0),
        total_trades=d.get("total_trades", 0),
        max_drawdown_pct=d.get("max_drawdown_pct", 0),
        max_drawdown_dollars=d.get("max_drawdown_dollars", 0),
        best_trade=d.get("best_trade", 0),
        worst_trade=d.get("worst_trade", 0),
        long_side_performance=d.get("long_side_performance", {}),
        short_side_performance=d.get("short_side_performance", {}),
        monthly_returns=d.get("monthly_returns", []),
        equity_curve=[],
        drawdown_curve=[],
        sharpe_ratio=d.get("sharpe_ratio", 0),
        sortino_ratio=d.get("sortino_ratio", 0),
        compliance_status=d.get("compliance_status", ""),
        compliance_reason=d.get("compliance_reason", ""),
    )
