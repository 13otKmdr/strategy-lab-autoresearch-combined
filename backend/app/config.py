from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "strategylab.db")
INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "50000"))
DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "15min")
RISK_LEVELS: list[float] = [0.25, 0.5]
STRATEGIES_PER_CYCLE: int = 50          # legacy v1
STRATEGIES_PER_ASSET: int = 150         # v2: per-asset generation
BATCHES_PER_CYCLE: int = 5
STRATEGIES_PER_BATCH: int = 10

# Data window
DATA_YEARS: float = 2.0
IS_SPLIT: float = 0.75                  # 18 months in-sample
OOS_SPLIT: float = 0.25                 # 6 months out-of-sample

# Drawdown compliance thresholds
MAX_DD_FUTURES: float = 0.04    # 4% = $2,000 on $50K
MAX_DD_CFD: float = 0.08        # 8% = $4,000 on $50K

# Backtesting constants
SLIPPAGE_PCT: float = 0.001     # 0.1% per side
COMMISSION_FLAT: float = 1.00   # $1 minimum
COMMISSION_PCT: float = 0.0005  # 0.05% of trade value
WARMUP_BARS: int = 200          # bars needed for longest indicator
