from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RankedStrategy:
    rank: int
    strategy_id: str
    strategy_name: str
    strategy_type: str
    market_type: str
    instrument: str

    # 0.25% risk results (summary)
    total_return_pct_025: float
    net_profit_dollars_025: float
    profit_factor_025: float
    max_drawdown_pct_025: float
    win_rate_025: float
    total_trades_025: int
    sharpe_ratio_025: float
    compliance_status_025: str

    # 0.5% risk results (summary)
    total_return_pct_050: float
    net_profit_dollars_050: float
    profit_factor_050: float
    max_drawdown_pct_050: float
    win_rate_050: float
    total_trades_050: int
    sharpe_ratio_050: float
    compliance_status_050: str

    # Composite
    composite_score: float
    overall_compliance: str

    # Monte Carlo eval
    eval_pass_rate: float = 0.0

    # Prop challenge path simulation (prop_challenge_sim)
    challenge_outcome: str = "timeout"          # "pass" | "fail_mll" | "fail_consistency" | "timeout"
    challenge_total_profit: float = 0.0
    challenge_days_traded: int = 0
    challenge_best_day_profit: float = 0.0
    challenge_consistency_passed: bool = False
    challenge_mll_breached: bool = False
    challenge_trades_taken: int = 0
    challenge_trades_skipped: int = 0

    # Analysis
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "market_type": self.market_type,
            "instrument": self.instrument,
            "total_return_pct_025": round(self.total_return_pct_025, 4),
            "net_profit_dollars_025": round(self.net_profit_dollars_025, 2),
            "profit_factor_025": round(self.profit_factor_025, 4),
            "max_drawdown_pct_025": round(self.max_drawdown_pct_025, 4),
            "win_rate_025": round(self.win_rate_025, 4),
            "total_trades_025": self.total_trades_025,
            "sharpe_ratio_025": round(self.sharpe_ratio_025, 4),
            "compliance_status_025": self.compliance_status_025,
            "total_return_pct_050": round(self.total_return_pct_050, 4),
            "net_profit_dollars_050": round(self.net_profit_dollars_050, 2),
            "profit_factor_050": round(self.profit_factor_050, 4),
            "max_drawdown_pct_050": round(self.max_drawdown_pct_050, 4),
            "win_rate_050": round(self.win_rate_050, 4),
            "total_trades_050": self.total_trades_050,
            "sharpe_ratio_050": round(self.sharpe_ratio_050, 4),
            "compliance_status_050": self.compliance_status_050,
            "composite_score": round(self.composite_score, 2),
            "overall_compliance": self.overall_compliance,
            "eval_pass_rate": round(self.eval_pass_rate, 4),
            "challenge_outcome": self.challenge_outcome,
            "challenge_total_profit": round(self.challenge_total_profit, 2),
            "challenge_days_traded": self.challenge_days_traded,
            "challenge_best_day_profit": round(self.challenge_best_day_profit, 2),
            "challenge_consistency_passed": self.challenge_consistency_passed,
            "challenge_mll_breached": self.challenge_mll_breached,
            "challenge_trades_taken": self.challenge_trades_taken,
            "challenge_trades_skipped": self.challenge_trades_skipped,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


@dataclass
class AssetResult:
    instrument: str
    instrument_name: str
    regime: str
    direction_bias: str
    regime_strength: float
    total_strategies: int
    total_tests: int
    compliant_count: int
    non_compliant_count: int
    best_profit_factor: float
    best_total_return: float
    avg_composite_score: float
    best_strategy_name: str = ""
    scout_data: dict = field(default_factory=dict)
    ranked_strategies: list[RankedStrategy] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "instrument_name": self.instrument_name,
            "regime": self.regime,
            "direction_bias": self.direction_bias,
            "regime_strength": round(self.regime_strength, 3),
            "total_strategies": self.total_strategies,
            "total_tests": self.total_tests,
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "best_profit_factor": round(self.best_profit_factor, 4),
            "best_total_return": round(self.best_total_return, 4),
            "avg_composite_score": round(self.avg_composite_score, 2),
            "best_strategy_name": self.best_strategy_name,
            "scout_data": self.scout_data,
            "ranked_strategies": [s.to_dict() for s in self.ranked_strategies],
        }


@dataclass
class CycleSummary:
    cycle_id: str
    timestamp: str
    assets: dict[str, AssetResult] = field(default_factory=dict)
    totals: dict = field(default_factory=dict)

    # Portfolio optimization result
    portfolio: dict = field(default_factory=dict)

    # Legacy flat fields (computed from assets)
    total_strategies: int = 0
    total_tests: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    best_profit_factor: float = 0.0
    best_total_return: float = 0.0
    avg_composite_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "assets": {k: v.to_dict() for k, v in self.assets.items()},
            "totals": self.totals,
            "portfolio": self.portfolio,
            "total_strategies": self.total_strategies,
            "total_tests": self.total_tests,
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "best_profit_factor": round(self.best_profit_factor, 4),
            "best_total_return": round(self.best_total_return, 4),
            "avg_composite_score": round(self.avg_composite_score, 2),
        }
