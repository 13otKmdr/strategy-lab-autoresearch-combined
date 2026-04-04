from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategyDefinition:
    strategy_id: str
    strategy_name: str
    strategy_type: str                          # "trend_following" | "mean_reversion" | "breakout" | "momentum" | "hybrid"
    market_type: str                            # "futures" | "cfd"
    thesis_summary: str
    indicators_used: list[dict]                 # [{"type": "RSI", "params": {"period": 14}}, ...]
    candlestick_patterns_used: list[str]        # ["engulfing", "doji", "hammer", ...]
    timeframe_stack: list[str]                  # ["15m"] initially
    entry_rules: dict                           # {"trigger": "RSI_OVERSOLD", "filter": "PRICE_ABOVE_EMA", "description": "..."}
    exit_rules: dict                            # {"stop_loss": {...}, "take_profit": {...}, "time_exit_bars": 48}
    stop_loss_logic: dict                       # {"type": "atr_multiple", "value": 2.0}
    take_profit_logic: dict                     # {"type": "r_multiple", "value": 2.5}
    trailing_stop_or_break_even_logic: dict     # {"type": "trailing_atr", "value": 1.5} or {"type": "break_even", "trigger_r": 1.0}
    session_filters: dict                       # {"allowed_sessions": ["us_open"], "avoid_first_minutes": 15}
    volatility_filters: dict                    # {"min_atr_percentile": 30, "max_atr_percentile": 90}
    fundamental_filters_if_any: dict            # {"avoid_fomc": true, "avoid_nfp": true} or {}
    intended_asset_classes: list[str]            # ["MES", "MNQ", ...]

    # Internal fields for the backtesting engine (maps to agent-network format)
    primary_indicator: dict = field(default_factory=dict)       # {"type": "RSI", "params": {"period": 14}}
    confirmation_indicator: dict = field(default_factory=dict)  # {"type": "EMA", "params": {"period": 50}}
    entry: dict = field(default_factory=dict)                   # {"trigger": "RSI_OVERSOLD", "filter": "PRICE_ABOVE_EMA"}
    exit: dict = field(default_factory=dict)                    # {"stop_loss": {...}, "take_profit": {...}, ...}
    risk: dict = field(default_factory=lambda: {"max_open_positions": 1})

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "market_type": self.market_type,
            "thesis_summary": self.thesis_summary,
            "indicators_used": self.indicators_used,
            "candlestick_patterns_used": self.candlestick_patterns_used,
            "timeframe_stack": self.timeframe_stack,
            "entry_rules": self.entry_rules,
            "exit_rules": self.exit_rules,
            "stop_loss_logic": self.stop_loss_logic,
            "take_profit_logic": self.take_profit_logic,
            "trailing_stop_or_break_even_logic": self.trailing_stop_or_break_even_logic,
            "session_filters": self.session_filters,
            "volatility_filters": self.volatility_filters,
            "fundamental_filters_if_any": self.fundamental_filters_if_any,
            "intended_asset_classes": self.intended_asset_classes,
        }


@dataclass
class StrategyBatch:
    batch_id: int                           # 1-5
    batch_type: str                         # "trend_following" | "mean_reversion" | "breakout" | "momentum" | "hybrid"
    strategies: list[StrategyDefinition]    # 10 strategies per batch
