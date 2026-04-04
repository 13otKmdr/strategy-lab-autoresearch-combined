export interface StrategyDefinition {
  strategy_id: string;
  strategy_name: string;
  strategy_type: string;
  market_type: string;
  thesis_summary: string;
  indicators_used: { type: string; params: Record<string, number> }[];
  candlestick_patterns_used: string[];
  timeframe_stack: string[];
  entry_rules: Record<string, string>;
  exit_rules: Record<string, unknown>;
  stop_loss_logic: Record<string, unknown>;
  take_profit_logic: Record<string, unknown>;
  trailing_stop_or_break_even_logic: Record<string, unknown>;
  session_filters: Record<string, unknown>;
  volatility_filters: Record<string, unknown>;
  fundamental_filters_if_any: Record<string, unknown>;
  intended_asset_classes: string[];
}

export interface BacktestResult {
  strategy_id: string;
  risk_pct: number;
  initial_capital: number;
  total_return_pct: number;
  net_profit_dollars: number;
  gross_profit: number;
  gross_loss: number;
  profit_factor: number;
  win_rate: number;
  avg_r_multiple: number;
  total_trades: number;
  max_drawdown_pct: number;
  max_drawdown_dollars: number;
  best_trade: number;
  worst_trade: number;
  long_side_performance: SidePerformance;
  short_side_performance: SidePerformance;
  monthly_returns: MonthlyReturn[];
  sharpe_ratio: number;
  sortino_ratio: number;
  compliance_status: string;
  compliance_reason: string;
  // OOS validation
  oos_total_return_pct: number;
  oos_net_profit_dollars: number;
  oos_profit_factor: number;
  oos_sharpe_ratio: number;
  oos_max_drawdown_pct: number;
  oos_total_trades: number;
  oos_win_rate: number;
  oos_compliance_status: string;
}

export interface SidePerformance {
  total_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
  avg_r_multiple: number;
}

export interface MonthlyReturn {
  month: string;
  return_pct: number;
  return_dollars: number;
}

export interface EquityCurveData {
  equity_curve_025: number[];
  equity_curve_050: number[];
  drawdown_curve_025: number[];
  drawdown_curve_050: number[];
}

export interface RankedStrategy {
  rank: number;
  strategy_id: string;
  strategy_name: string;
  strategy_type: string;
  market_type: string;
  instrument: string;
  total_return_pct_025: number;
  net_profit_dollars_025: number;
  profit_factor_025: number;
  max_drawdown_pct_025: number;
  win_rate_025: number;
  total_trades_025: number;
  sharpe_ratio_025: number;
  compliance_status_025: string;
  total_return_pct_050: number;
  net_profit_dollars_050: number;
  profit_factor_050: number;
  max_drawdown_pct_050: number;
  win_rate_050: number;
  total_trades_050: number;
  sharpe_ratio_050: number;
  compliance_status_050: string;
  composite_score: number;
  overall_compliance: string;
  eval_pass_rate: number;
  strengths: string[];
  weaknesses: string[];
}

export interface AssetRegime {
  instrument: string;
  symbol: string;
  regime: string;
  direction_bias: string;
  strength: number;
  current_price: number;
  price_change_pct: number;
  sentiment_score: number;
  sentiment_label: string;
  best_strategy_family: string;
  worst_strategy_family: string;
  buy_and_hold_2y: number;
}

export interface AssetResult {
  instrument: string;
  instrument_name: string;
  regime: string;
  direction_bias: string;
  regime_strength: number;
  total_strategies: number;
  total_tests: number;
  compliant_count: number;
  non_compliant_count: number;
  best_profit_factor: number;
  best_total_return: number;
  avg_composite_score: number;
  best_strategy_name: string;
  scout_data: AssetRegime;
  ranked_strategies: RankedStrategy[];
}

export interface PortfolioStrategy {
  strategy_id: string;
  name: string;
  instrument: string;
  weight: number;
}

export interface PortfolioResult {
  strategies: PortfolioStrategy[];
  combined_return_pct: number;
  combined_net_profit: number;
  combined_max_dd_pct: number;
  combined_max_dd_dollars: number;
  combined_sharpe: number;
  combined_profit_factor: number;
  combined_trades: number;
  diversification_score: number;
  compliance_status: string;
  correlation_matrix: number[][];
}

export interface CycleSummary {
  cycle_id: string;
  timestamp: string;
  assets: Record<string, AssetResult>;
  totals: { total_strategies: number; total_tests: number; elapsed_seconds: number };
  portfolio: PortfolioResult | null;
  total_strategies: number;
  total_tests: number;
  compliant_count: number;
  non_compliant_count: number;
  best_profit_factor: number;
  best_total_return: number;
  avg_composite_score: number;
}

export interface StrategyDetail {
  strategy: StrategyDefinition;
  result_025: BacktestResult;
  result_050: BacktestResult;
  equity_data: EquityCurveData;
  strengths: string[];
  weaknesses: string[];
}

export type SortField =
  | 'composite_score'
  | 'profit_factor_025'
  | 'profit_factor_050'
  | 'net_profit_dollars_025'
  | 'net_profit_dollars_050'
  | 'total_return_pct_025'
  | 'total_return_pct_050'
  | 'max_drawdown_pct_025'
  | 'max_drawdown_pct_050'
  | 'win_rate_025'
  | 'win_rate_050';

export interface Filters {
  search: string;
  marketType: string;
  complianceOnly: boolean;
  minProfitFactor: number;
  minTotalProfit: number;
  strategyType: string;
  sortBy: SortField;
  sortDir: 'asc' | 'desc';
  riskView: '025' | '050';
}

export const INSTRUMENTS = ['MES', 'MNQ', 'MYM', 'MGC', 'MCL'] as const;

export const INSTRUMENT_NAMES: Record<string, string> = {
  MES: 'S&P 500',
  MNQ: 'Nasdaq 100',
  MYM: 'Dow Jones',
  MGC: 'Gold',
  MCL: 'Crude Oil',
};

export const REGIME_COLORS: Record<string, string> = {
  trending_up: 'text-accent-green',
  trending_down: 'text-accent-red',
  ranging: 'text-accent-amber',
  volatile: 'text-accent-purple',
};

export const REGIME_LABELS: Record<string, string> = {
  trending_up: 'Trending Up',
  trending_down: 'Trending Down',
  ranging: 'Ranging',
  volatile: 'Volatile',
};
