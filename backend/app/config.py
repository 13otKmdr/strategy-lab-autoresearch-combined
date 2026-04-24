from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "strategylab.db")
INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "50000"))
DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "15min")
def _float_list_from_env(name: str, default: str) -> list[float]:
    return [float(s.strip()) for s in os.getenv(name, default).split(",") if s.strip()]


# Under the prop profile these are Daily Risk Budget multiples, not account %.
# Example: 0.25 means 0.25x DRB.  Values > 10 may be passed as explicit dollars.
PROP_RISK_MULTIPLES: list[float] = _float_list_from_env("PROP_RISK_MULTIPLES", "0.25,0.5")
PROP_RISK_DOLLARS: list[float] = _float_list_from_env("PROP_RISK_DOLLARS", "")
RISK_LEVELS: list[float] = PROP_RISK_DOLLARS or PROP_RISK_MULTIPLES
PROP_PROFILE: str = os.getenv("PROP_PROFILE", "prop_done_right_tdg")
PROP_ALLOWED_SYMBOLS: tuple[str, ...] = tuple(
    s.strip().upper() for s in os.getenv("PROP_ALLOWED_SYMBOLS", "MYM").split(",") if s.strip()
)
PROP_BLOCKED_SYMBOLS: tuple[str, ...] = tuple(
    s.strip().upper() for s in os.getenv("PROP_BLOCKED_SYMBOLS", "MNQ,NQ,ES,YM,RTY").split(",") if s.strip()
)
PROP_ALLOW_ETF_PROXY_DATA: bool = os.getenv("PROP_ALLOW_ETF_PROXY_DATA", "false").lower() in {"1", "true", "yes", "on"}
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

# ProjectX / TopstepX API
TOPSTEPX_BASE_URL: str = os.getenv("TOPSTEPX_BASE_URL", "https://api.topstepx.com")
TOPSTEPX_EMAIL: str = os.getenv("TOPSTEPX_EMAIL", "")
TOPSTEPX_API_KEY: str = os.getenv("TOPSTEPX_API_KEY", "")
TOPSTEPX_ACCOUNT_ID: int = int(os.getenv("TOPSTEPX_ACCOUNT_ID", "0"))

# Data source: "projectx" for real futures data, "twelvedata" for ETF proxies
DATA_SOURCE: str = os.getenv("DATA_SOURCE", "projectx")

# Live trading safety gates
LIVE_FEATURE_FLAG: bool = os.getenv("LIVE_FEATURE_FLAG", "false").lower() in {"1", "true", "yes", "on"}
LIVE_ARMING_TOKEN: str = os.getenv("LIVE_ARMING_TOKEN", "")
LIVE_ALLOWLISTED_ACCOUNTS: set[str] = set(
    s.strip() for s in os.getenv("LIVE_ALLOWLISTED_ACCOUNTS", "").split(",") if s.strip()
)
