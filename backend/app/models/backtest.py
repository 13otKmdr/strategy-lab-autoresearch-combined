from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    size: float
    direction: str              # "long" | "short"
    pnl: float                  # USD P&L after commission
    pnl_pct: float              # fraction of equity at entry
    r_multiple: float           # pnl / initial_risk_usd
    exit_reason: str            # "stop_loss" | "take_profit" | "trailing_stop" | "time_exit" | "end_of_data"
    entry_ts: int               # Unix ms
    exit_ts: int
    regime: str = "unknown"     # "bull" | "bear" | "sideways"


@dataclass
class SidePerformance:
    total_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    avg_r_multiple: float


@dataclass
class BacktestConfig:
    strategy_id: str
    risk_pct: float             # Prop profile: DRB multiple (0.25 = 25% of DRB); legacy name kept for API compatibility
    initial_capital: float      # 50000
    instrument: str             # "MES", "MNQ", etc.
    timeframe: str              # "15min"


@dataclass
class BacktestResult:
    strategy_id: str
    risk_pct: float
    initial_capital: float

    # Returns
    total_return_pct: float
    net_profit_dollars: float
    gross_profit: float
    gross_loss: float

    # Performance
    profit_factor: float
    win_rate: float
    avg_r_multiple: float
    total_trades: int

    # Risk
    max_drawdown_pct: float
    max_drawdown_dollars: float

    # Extremes
    best_trade: float           # best single trade P&L $
    worst_trade: float          # worst single trade P&L $

    # Side analysis
    long_side_performance: dict
    short_side_performance: dict

    # Time series
    monthly_returns: list[dict]     # [{"month": "2025-01", "return_pct": 1.2, "return_dollars": 600}, ...]
    equity_curve: list[float]
    drawdown_curve: list[float]

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float

    # Compliance
    compliance_status: str          # "compliant" | "non_compliant"
    compliance_reason: str          # "" if compliant, reason if not

    # Out-of-sample validation (6 months)
    oos_total_return_pct: float = 0.0
    oos_net_profit_dollars: float = 0.0
    oos_profit_factor: float = 0.0
    oos_sharpe_ratio: float = 0.0
    oos_max_drawdown_pct: float = 0.0
    oos_total_trades: int = 0
    oos_win_rate: float = 0.0
    oos_compliance_status: str = ""

    # Trade list
    trades: list[Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "risk_pct": self.risk_pct,
            "initial_capital": self.initial_capital,
            "total_return_pct": round(self.total_return_pct, 4),
            "net_profit_dollars": round(self.net_profit_dollars, 2),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "profit_factor": round(self.profit_factor, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_r_multiple": round(self.avg_r_multiple, 4),
            "total_trades": self.total_trades,
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "max_drawdown_dollars": round(self.max_drawdown_dollars, 2),
            "best_trade": round(self.best_trade, 2),
            "worst_trade": round(self.worst_trade, 2),
            "long_side_performance": self.long_side_performance,
            "short_side_performance": self.short_side_performance,
            "monthly_returns": self.monthly_returns,
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "compliance_status": self.compliance_status,
            "compliance_reason": self.compliance_reason,
            # OOS validation
            "oos_total_return_pct": round(self.oos_total_return_pct, 4),
            "oos_net_profit_dollars": round(self.oos_net_profit_dollars, 2),
            "oos_profit_factor": round(self.oos_profit_factor, 4),
            "oos_sharpe_ratio": round(self.oos_sharpe_ratio, 4),
            "oos_max_drawdown_pct": round(self.oos_max_drawdown_pct, 4),
            "oos_total_trades": self.oos_total_trades,
            "oos_win_rate": round(self.oos_win_rate, 4),
            "oos_compliance_status": self.oos_compliance_status,
            # equity_curve and drawdown_curve excluded from default dict (too large)
            # fetch via /strategies/:id/equity endpoint
        }
