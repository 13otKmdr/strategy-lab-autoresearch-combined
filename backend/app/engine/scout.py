"""
Market intelligence scout using TradingView MCP.

Analyzes each asset's current regime, sentiment, and active signals
BEFORE strategy generation. This enables regime-tuned strategy creation
instead of blind combinatorial generation.

Uses: tradingview-mcp-server (Yahoo Finance + TradingView TA + Reddit sentiment)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.models.market import INSTRUMENTS

logger = logging.getLogger(__name__)

# Map our internal instrument codes to Yahoo Finance / TradingView symbols
_SYMBOL_MAP = {
    "MES": "SPY",
    "MNQ": "QQQ",
    "MYM": "DIA",
    "MGC": "GLD",
    "MCL": "USO",
}


@dataclass
class AssetRegime:
    instrument: str
    symbol: str                                 # Yahoo symbol used for scouting
    regime: str                                 # "trending_up" | "trending_down" | "ranging" | "volatile"
    direction_bias: str                         # "bullish" | "bearish" | "neutral"
    strength: float                             # 0-1 confidence in regime classification
    current_price: float = 0.0
    price_change_pct: float = 0.0
    week52_high: float = 0.0
    week52_low: float = 0.0
    sentiment_score: float = 0.0                # -1 (bearish) to +1 (bullish)
    sentiment_label: str = "neutral"
    strategy_rankings: list[dict] = field(default_factory=list)  # compare_strategies results
    best_strategy_family: str = ""
    worst_strategy_family: str = ""
    active_signals: list[str] = field(default_factory=list)
    buy_and_hold_2y: float = 0.0
    scout_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "symbol": self.symbol,
            "regime": self.regime,
            "direction_bias": self.direction_bias,
            "strength": round(self.strength, 3),
            "current_price": self.current_price,
            "price_change_pct": self.price_change_pct,
            "week52_high": self.week52_high,
            "week52_low": self.week52_low,
            "sentiment_score": self.sentiment_score,
            "sentiment_label": self.sentiment_label,
            "strategy_rankings": self.strategy_rankings,
            "best_strategy_family": self.best_strategy_family,
            "worst_strategy_family": self.worst_strategy_family,
            "active_signals": self.active_signals,
            "buy_and_hold_2y": self.buy_and_hold_2y,
            "scout_timestamp": self.scout_timestamp,
        }


def scout_asset(instrument: str) -> AssetRegime:
    """
    Scout a single asset using TradingView MCP tools.
    Returns a regime classification with market context.
    """
    symbol = _SYMBOL_MAP.get(instrument, instrument)
    logger.info("Scouting %s (%s)...", instrument, symbol)

    regime = AssetRegime(
        instrument=instrument,
        symbol=symbol,
        regime="ranging",
        direction_bias="neutral",
        strength=0.5,
    )

    try:
        from tradingview_mcp import server
    except ImportError:
        logger.warning("tradingview_mcp not available — returning default regime for %s", instrument)
        return regime

    from datetime import datetime, timezone
    regime.scout_timestamp = datetime.now(timezone.utc).isoformat()

    # 1. Get current price
    try:
        price_data = server.yahoo_price(symbol)
        regime.current_price = price_data.get("price", 0)
        regime.price_change_pct = price_data.get("change_pct", 0)
        regime.week52_high = price_data.get("52w_high", 0)
        regime.week52_low = price_data.get("52w_low", 0)
        logger.info("  %s price: $%.2f (%+.2f%%)", symbol, regime.current_price, regime.price_change_pct)
    except Exception as e:
        logger.warning("  Price fetch failed for %s: %s", symbol, e)
    time.sleep(1)

    # 2. Compare 6 strategies (2-year backtest)
    try:
        comp = server.compare_strategies(symbol, period="2y", initial_capital=50000, interval="1d")
        regime.buy_and_hold_2y = comp.get("buy_and_hold_return_pct", 0)

        rankings = comp.get("ranking", [])
        regime.strategy_rankings = rankings

        # Identify best and worst families
        profitable = [r for r in rankings if r.get("total_trades", 0) > 0 and r.get("total_return_pct", 0) > 0]
        losers = [r for r in rankings if r.get("total_trades", 0) > 0 and r.get("total_return_pct", 0) < 0]

        if profitable:
            best = max(profitable, key=lambda r: r.get("total_return_pct", 0))
            regime.best_strategy_family = best.get("strategy", "")
        if losers:
            worst = min(losers, key=lambda r: r.get("total_return_pct", 0))
            regime.worst_strategy_family = worst.get("strategy", "")

        # Derive active signals from top strategies
        for r in rankings[:3]:
            strat = r.get("strategy", "")
            ret = r.get("total_return_pct", 0)
            if ret > 0:
                regime.active_signals.append(f"{strat}_PROFITABLE")

        logger.info("  %s B&H: %.1f%%, best: %s, worst: %s",
                     symbol, regime.buy_and_hold_2y, regime.best_strategy_family, regime.worst_strategy_family)
    except Exception as e:
        logger.warning("  Strategy comparison failed for %s: %s", symbol, e)
    time.sleep(1)

    # 3. Sentiment analysis
    try:
        sent = server.analyze_sentiment(symbol, limit=15)
        raw_score = sent.get("sentiment_score", 0)
        regime.sentiment_score = raw_score
        regime.sentiment_label = sent.get("sentiment_label", "neutral")
        logger.info("  %s sentiment: %s (%.3f)", symbol, regime.sentiment_label, raw_score)
    except Exception as e:
        logger.warning("  Sentiment failed for %s: %s", symbol, e)
    time.sleep(1)

    # 4. Classify regime from all gathered data
    regime.regime, regime.direction_bias, regime.strength = _classify_regime(regime)
    logger.info("  %s regime: %s, bias: %s, strength: %.2f",
                 instrument, regime.regime, regime.direction_bias, regime.strength)

    return regime


def scout_all_assets() -> dict[str, AssetRegime]:
    """Scout all 5 assets and return a dict keyed by instrument code."""
    results = {}
    for instrument in INSTRUMENTS:
        results[instrument] = scout_asset(instrument)
    return results


def _classify_regime(regime: AssetRegime) -> tuple[str, str, float]:
    """
    Classify asset regime from price data, strategy comparison, and sentiment.

    Returns (regime_type, direction_bias, confidence).
    """
    bh = regime.buy_and_hold_2y
    price = regime.current_price
    w52h = regime.week52_high
    w52l = regime.week52_low
    sent = regime.sentiment_score
    best = regime.best_strategy_family
    worst = regime.worst_strategy_family
    rankings = regime.strategy_rankings

    # Price position within 52-week range (0 = at low, 1 = at high)
    if w52h > w52l and price > 0:
        price_position = (price - w52l) / (w52h - w52l)
    else:
        price_position = 0.5

    # Strategy performance analysis
    trend_strats_profitable = any(
        r.get("strategy") in ("ema_cross", "supertrend") and r.get("total_return_pct", 0) > 5
        for r in rankings
    )
    meanrev_strats_profitable = any(
        r.get("strategy") in ("bollinger", "rsi") and r.get("total_return_pct", 0) > 5
        for r in rankings
    )
    # Check if trend strategies lost badly
    trend_strats_lost = any(
        r.get("strategy") in ("ema_cross", "supertrend") and r.get("total_return_pct", 0) < -10
        for r in rankings
    )

    # Max drawdown from worst strategy
    max_dd = max((abs(r.get("max_drawdown_pct", 0)) for r in rankings), default=0)

    # Regime classification
    confidence = 0.5

    if bh > 30 and trend_strats_profitable and price_position > 0.6:
        regime_type = "trending_up"
        confidence = min(0.9, 0.5 + bh / 200)
    elif bh < -10 and trend_strats_lost and price_position < 0.4:
        regime_type = "trending_down"
        confidence = min(0.9, 0.5 + abs(bh) / 200)
    elif max_dd > 20 or (trend_strats_lost and not meanrev_strats_profitable):
        regime_type = "volatile"
        confidence = min(0.8, 0.5 + max_dd / 100)
    elif meanrev_strats_profitable and not trend_strats_profitable:
        regime_type = "ranging"
        confidence = 0.6
    elif trend_strats_profitable and meanrev_strats_profitable:
        # Both work — moderate trend with pullback opportunities
        regime_type = "trending_up" if bh > 0 else "trending_down"
        confidence = 0.55
    else:
        regime_type = "ranging"
        confidence = 0.4

    # Direction bias from sentiment + price action
    if sent > 0.3 and price_position > 0.5:
        direction = "bullish"
    elif sent < -0.3 and price_position < 0.5:
        direction = "bearish"
    elif bh > 20:
        direction = "bullish"
    elif bh < -10:
        direction = "bearish"
    else:
        direction = "neutral"

    return regime_type, direction, confidence
