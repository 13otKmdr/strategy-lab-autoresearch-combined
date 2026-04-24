"""
Cycle API endpoints — v2 per-asset intelligence-first pipeline.

POST /api/cycles/run — Scout all assets → generate per-asset → backtest IS/OOS → rank
GET  /api/cycles — list all cycles
GET  /api/cycles/:id — get cycle detail with per-asset results
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import (
    INITIAL_CAPITAL,
    IS_SPLIT,
    PROP_ALLOWED_SYMBOLS,
    PROP_BLOCKED_SYMBOLS,
    PROP_PROFILE,
    RISK_LEVELS,
    STRATEGIES_PER_ASSET,
)
from app.data import storage
from app.data.mock_data import generate_mock_candles
from app.data.twelvedata import fetch_2y_candles, fetch_candles
from app.engine.backtester import run_backtest
from app.engine.compliance import check_compliance
from app.engine.generator import generate_for_asset
from app.engine.orb import run_orb_backtest, orb_config_from_strategy
from app.engine.portfolio import optimize_portfolio
from app.engine.prop_profile import select_instruments
from app.engine.ranker import rank_strategies
from app.engine.scout import AssetRegime, scout_all_assets
from app.engine.session_rotation import run_session_backtest, SessionRotationConfig
from app.engine.vwap_reversion import run_vwap_backtest
from app.models.market import Candle, INSTRUMENTS
from app.models.ranking import AssetResult, CycleSummary

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/cycles/run")
async def run_cycle():
    """
    Intelligence-first per-asset cycle:
    1. Scout all assets (TradingView MCP)
    2. For each asset: generate regime-tuned strategies → backtest IS/OOS → rank
    3. Return per-asset results with global totals
    """
    storage.init_db()

    cycle_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    logger.info("Starting v2 cycle %s", cycle_id)

    enabled_instruments = select_instruments(
        tuple(INSTRUMENTS.keys()),
        profile=PROP_PROFILE,
        allowed_symbols=PROP_ALLOWED_SYMBOLS,
        blocked_symbols=PROP_BLOCKED_SYMBOLS,
    )
    logger.info("Active prop profile %s enabled instruments: %s", PROP_PROFILE, ", ".join(enabled_instruments))

    # Phase 1: Scout all assets
    logger.info("Phase 1: Scouting all assets...")
    scout_start = time.time()
    try:
        regimes = scout_all_assets()
    except Exception as e:
        logger.warning("Scout failed: %s — using default regimes", e)
        regimes = {
            inst: AssetRegime(instrument=inst, symbol=inst, regime="ranging", direction_bias="neutral", strength=0.5)
            for inst in enabled_instruments
        }
    logger.info("Scout complete in %.1fs", time.time() - scout_start)

    # Phase 2: Per-asset generation, backtesting, ranking
    asset_results: dict[str, AssetResult] = {}
    all_results_cache: dict[str, dict[float, any]] = {}  # strategy_id -> {risk_pct: BacktestResult}
    total_strategies = 0
    total_tests = 0
    seed = int(time.time())

    for instrument in enabled_instruments:
        asset_start = time.time()
        regime = regimes.get(instrument, AssetRegime(
            instrument=instrument, symbol=instrument, regime="ranging",
            direction_bias="neutral", strength=0.5,
        ))
        inst_spec = INSTRUMENTS[instrument]
        logger.info("Processing %s (%s) — regime: %s, bias: %s",
                     instrument, inst_spec["name"], regime.regime, regime.direction_bias)

        # Fetch candle data (2 years with cache, fall back to shorter window or mock)
        candles: list[Candle] = []
        try:
            candles = await fetch_2y_candles(instrument, "15min", use_cache=True)
        except Exception as e:
            logger.warning("2y fetch failed for %s: %s", instrument, e)

        if not candles:
            try:
                candles = await fetch_candles(instrument, "15min", 5000)
            except Exception:
                pass

        if not candles or len(candles) < 500:
            logger.info("Using mock data for %s", instrument)
            candles = generate_mock_candles(instrument, num_candles=5000, seed=hash(instrument) % 10000)

        # IS/OOS split
        split_idx = int(len(candles) * IS_SPLIT)
        is_candles = candles[:split_idx]
        oos_candles = candles[split_idx:]
        logger.info("  Data: %d total candles, %d IS, %d OOS", len(candles), len(is_candles), len(oos_candles))

        # Generate strategies
        strategies = generate_for_asset(instrument, regime, seed + hash(instrument), STRATEGIES_PER_ASSET)
        logger.info("  Generated %d strategies for %s", len(strategies), instrument)

        # Backtest each strategy at both risk levels (IS + OOS)
        results: dict[str, dict[float, any]] = {}
        asset_test_count = 0

        for strat in strategies:
            results[strat.strategy_id] = {}

            for risk_pct in RISK_LEVELS:
                # Route to correct backtester based on strategy type
                is_result = _run_strategy_backtest(strat, is_candles, risk_pct, INITIAL_CAPITAL)

                # Out-of-sample backtest
                if len(oos_candles) > 300:
                    oos_result = _run_strategy_backtest(strat, oos_candles, risk_pct, INITIAL_CAPITAL)
                    is_result.oos_total_return_pct = oos_result.total_return_pct
                    is_result.oos_net_profit_dollars = oos_result.net_profit_dollars
                    is_result.oos_profit_factor = oos_result.profit_factor
                    is_result.oos_sharpe_ratio = oos_result.sharpe_ratio
                    is_result.oos_max_drawdown_pct = oos_result.max_drawdown_pct
                    is_result.oos_total_trades = oos_result.total_trades
                    is_result.oos_win_rate = oos_result.win_rate
                    oos_compliance = check_compliance(oos_result.max_drawdown_pct, strat.market_type)
                    is_result.oos_compliance_status = oos_compliance["status"]

                results[strat.strategy_id][risk_pct] = is_result
                asset_test_count += 1

                # Save to DB
                storage.save_backtest_result(
                    strat.strategy_id, cycle_id, risk_pct,
                    is_result.to_dict(),
                    is_result.equity_curve,
                    is_result.drawdown_curve,
                )

            storage.save_strategy(strat.strategy_id, cycle_id, strat.to_dict())

        # Cache results for cross-asset portfolio optimization
        all_results_cache.update(results)

        # Rank strategies for this asset (includes deterministic challenge sim
        # and Monte Carlo pass probability on every strategy)
        ranked = rank_strategies(strategies, results)

        for r in ranked:
            storage.save_ranking(r.strategy_id, cycle_id, r.rank, r.to_dict())

        # Build asset result
        compliant = sum(1 for r in ranked if r.overall_compliance == "compliant")
        non_compliant = len(ranked) - compliant
        best_pf = max((r.profit_factor_025 for r in ranked), default=0)
        best_return = max((r.total_return_pct_025 for r in ranked), default=0)
        avg_score = sum(r.composite_score for r in ranked) / len(ranked) if ranked else 0

        asset_result = AssetResult(
            instrument=instrument,
            instrument_name=inst_spec["name"],
            regime=regime.regime,
            direction_bias=regime.direction_bias,
            regime_strength=regime.strength,
            total_strategies=len(strategies),
            total_tests=asset_test_count,
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            best_profit_factor=best_pf,
            best_total_return=best_return,
            avg_composite_score=avg_score,
            best_strategy_name=ranked[0].strategy_name if ranked else "",
            scout_data=regime.to_dict(),
            ranked_strategies=ranked,
        )
        asset_results[instrument] = asset_result
        total_strategies += len(strategies)
        total_tests += asset_test_count

        logger.info("  %s complete: %d strategies, %d tests, %d compliant, best PF %.2f (%.1fs)",
                     instrument, len(strategies), asset_test_count, compliant, best_pf, time.time() - asset_start)

    # Portfolio optimization across all assets
    all_candidates = []
    for instrument_key, asset_result in asset_results.items():
        for ranked_strat in asset_result.ranked_strategies[:10]:
            bt = all_results_cache.get(ranked_strat.strategy_id, {}).get(0.25)
            if bt:
                all_candidates.append((ranked_strat, bt))
    portfolio_dict = {}
    if len(all_candidates) >= 2:
        try:
            portfolio_result = optimize_portfolio(all_candidates, max_strategies=3)
            if portfolio_result:
                portfolio_dict = portfolio_result.to_dict()
                logger.info("Portfolio optimized: %d strategies, Sharpe %.2f, DD %.2f%%",
                            len(portfolio_result.strategies), portfolio_result.combined_sharpe,
                            portfolio_result.combined_max_dd_pct * 100)
        except Exception as exc:
            logger.warning("Portfolio optimization failed: %s", exc)

    # Build cycle summary
    elapsed = round(time.time() - start_time, 1)
    all_compliant = sum(ar.compliant_count for ar in asset_results.values())
    all_non_compliant = sum(ar.non_compliant_count for ar in asset_results.values())
    all_pf = max((ar.best_profit_factor for ar in asset_results.values()), default=0)
    all_return = max((ar.best_total_return for ar in asset_results.values()), default=0)
    all_scores = [ar.avg_composite_score for ar in asset_results.values() if ar.avg_composite_score > 0]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

    summary = CycleSummary(
        cycle_id=cycle_id,
        timestamp=timestamp,
        assets=asset_results,
        totals={"total_strategies": total_strategies, "total_tests": total_tests, "elapsed_seconds": elapsed},
        portfolio=portfolio_dict,
        total_strategies=total_strategies,
        total_tests=total_tests,
        compliant_count=all_compliant,
        non_compliant_count=all_non_compliant,
        best_profit_factor=all_pf,
        best_total_return=all_return,
        avg_composite_score=avg_score,
    )

    storage.save_cycle(cycle_id, timestamp, summary.to_dict())
    logger.info("Cycle %s complete: %d strategies, %d tests, %d compliant, %.1fs",
                 cycle_id, total_strategies, total_tests, all_compliant, elapsed)

    return summary.to_dict()


def _run_strategy_backtest(strat, candles, risk_pct, capital):
    """Route to the correct backtester based on strategy entry trigger."""
    trigger = strat.entry.get("trigger", "")

    if trigger == "ORB_BREAKOUT":
        config = orb_config_from_strategy(strat)
        return run_orb_backtest(config, candles, risk_pct, capital)

    if trigger == "VWAP_REVERSION":
        return run_vwap_backtest(
            candles,
            distance_threshold_atr=strat.entry.get("distance_threshold_atr", 2.0),
            direction=strat.entry.get("direction", "both"),
            stop_buffer_atr=strat.exit.get("stop_buffer_atr", 1.0),
            tp_mode=strat.exit.get("tp_mode", "vwap"),
            session_filter=strat.session_filters.get("session_filter", "midday_only"),
            risk_pct=risk_pct,
            initial_capital=capital,
            strategy_id=strat.strategy_id,
            market_type=strat.market_type,
            symbol=strat.intended_asset_classes[0] if strat.intended_asset_classes else "MYM",
        )

    if strat.strategy_id.startswith("SESS-"):
        # Build SessionRotationConfig from strategy definition
        entry_rules = strat.entry_rules
        morning = entry_rules.get("morning", {})
        midday = entry_rules.get("midday", {})
        afternoon = entry_rules.get("afternoon", {})
        session_config = SessionRotationConfig(
            symbol=strat.intended_asset_classes[0] if strat.intended_asset_classes else "MYM",
            morning_trigger=morning.get("trigger", "DC_UPPER_BREAK"),
            morning_filter=morning.get("filter", "ATR_EXPANDING"),
            midday_trigger=midday.get("trigger", "RSI_OVERSOLD"),
            midday_filter=midday.get("filter", "PRICE_ABOVE_EMA"),
            afternoon_trigger=afternoon.get("trigger", "MACD_CROSS_ABOVE"),
            afternoon_filter=afternoon.get("filter", "ADX_TRENDING"),
            daily_loss_limit=strat.session_filters.get("daily_loss_limit", 500.0),
            stop_loss_value=strat.stop_loss_logic.get("value", 2.0),
            take_profit_value=strat.take_profit_logic.get("value", 2.0),
        )
        return run_session_backtest(session_config, candles, risk_pct, capital)

    # Default: indicator-based strategy
    return run_backtest(strat, candles, risk_pct, capital, strat.market_type)


@router.get("/cycles")
async def list_cycles():
    """List all completed cycles."""
    storage.init_db()
    return storage.get_cycles()


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str):
    """Get full cycle summary with per-asset results."""
    storage.init_db()
    data = storage.get_cycle(cycle_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return data
