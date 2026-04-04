"""
Drawdown compliance checker for prop firm rules.

Futures: max 4% drawdown ($2,000 on $50K)
CFD: max 8% drawdown ($4,000 on $50K)
"""
from __future__ import annotations

from app.config import MAX_DD_CFD, MAX_DD_FUTURES


def check_compliance(max_drawdown_pct: float, market_type: str) -> dict:
    """Check if a strategy's max drawdown is within prop firm limits."""
    threshold = MAX_DD_FUTURES if market_type == "futures" else MAX_DD_CFD
    label = f"{threshold * 100:.0f}%"

    if max_drawdown_pct <= threshold:
        return {"status": "compliant", "reason": ""}
    else:
        return {
            "status": "non_compliant",
            "reason": f"Max drawdown {max_drawdown_pct * 100:.2f}% exceeds {market_type} limit of {label}",
        }
