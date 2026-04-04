"""
Cross-Account Hedge Simulator v3 — Trade-by-Trade Model.

Replaces the bar-by-bar price-drift simulator with discrete trade outcomes
derived from the strategy's win rate and risk:reward ratio.

WHY: The price-drift model (v2) accumulated trailing DD from volatility
oscillations even in flat markets, making results depend on price noise
rather than strategy quality. This model uses only:
  - Win rate (probability each trade is a winner)
  - R:R ratio (reward size relative to risk size)
  - Risk per trade (fixed $ amount risked)

Mirrored hedge logic: futures and CFD take opposite sides of every trade.
When one wins, the other loses the same magnitude (minus commissions).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT PRESETS
# ═══════════════════════════════════════════════════════════════════════════════

FUTURES_50K: dict = {
    "account_size": 50_000,
    "profit_target": 3_000,
    "max_dd": 2_000,
    "daily_limit": 1_000,
    "challenge_cost": 70,
    "commission": 5,
}

CFD_50K: dict = {
    "account_size": 50_000,
    "profit_target": 5_000,
    "max_dd": 3_000,
    "daily_limit": 0,
    "challenge_cost": 75,
    "commission": 3,
}


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HedgeTradeConfig:
    strategy_win_rate: float       # e.g. 0.55
    strategy_rr: float             # e.g. 2.0 (risk:reward)
    risk_per_trade: float          # $ risked per trade, e.g. $250
    trades_per_day: float          # e.g. 2.0
    futures_config: dict           # FUTURES_50K style dict
    cfd_config: dict               # CFD_50K style dict
    payout_split: float = 0.85    # firm keeps 15%


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HedgeTradeResult:
    # Inputs echoed back
    n_sims: int
    win_rate_used: float
    rr_used: float

    # Outcome rates
    futures_pass_rate: float
    cfd_pass_rate: float
    combined_win_rate: float
    both_blown_rate: float
    timeout_rate: float

    # Economics (after payout split and challenge fees)
    avg_profit_futures_win: float
    avg_profit_cfd_win: float
    expected_value_per_attempt: float
    roi_per_attempt: float

    # Timing
    avg_days_to_resolve: float

    # Derived
    break_even_win_rate: float
    monthly_ev: float
    annual_ev: float


# ═══════════════════════════════════════════════════════════════════════════════
# CORE SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_hedge_trades(
    config: HedgeTradeConfig,
    n_sims: int = 5_000,
    max_days: int = 30,
    seed: int = 42,
) -> HedgeTradeResult:
    """
    Simulate the cross-account hedge using discrete trade outcomes.

    For each simulation run:
    - Generate trades_per_day * max_days trades
    - Each trade is WIN (prob = win_rate) or LOSS
    - Futures and CFD are mirrored: one gains what the other loses
    - Track trailing DD (sticky — once blown, account is dead)
    - Check profit targets, DD limits, daily loss limits
    """
    rng = np.random.default_rng(seed)

    fc = config.futures_config
    cc = config.cfd_config
    total_cost = fc["challenge_cost"] + cc["challenge_cost"]

    trades_per_day = max(1, round(config.trades_per_day))
    total_trades = trades_per_day * max_days

    # Pre-generate all random outcomes for vectorized speed
    # Shape: (n_sims, total_trades) — True = strategy WIN
    outcomes = rng.random((n_sims, total_trades)) < config.strategy_win_rate

    # Accumulators
    futures_wins = 0
    cfd_wins = 0
    both_blown = 0
    timeouts = 0

    profits_futures_win: list[float] = []
    profits_cfd_win: list[float] = []
    days_to_resolve: list[float] = []

    risk = config.risk_per_trade
    reward = config.risk_per_trade * config.strategy_rr
    f_comm = fc["commission"]
    c_comm = cc["commission"]

    for sim in range(n_sims):
        # Per-account state
        f_pnl = 0.0
        c_pnl = 0.0
        f_peak = 0.0
        c_peak = 0.0
        f_blown = False
        c_blown = False
        f_passed = False
        c_passed = False

        day_f_pnl = 0.0
        day_c_pnl = 0.0
        resolved = False
        resolve_day = max_days

        for t in range(total_trades):
            trade_day = t // trades_per_day
            trade_in_day = t % trades_per_day

            # Reset daily P&L at start of each new day
            if trade_in_day == 0:
                day_f_pnl = 0.0
                day_c_pnl = 0.0

            is_win = outcomes[sim, t]

            # Strategy WIN: futures side gains reward, CFD side loses reward
            # Strategy LOSS: futures side loses risk, CFD side gains risk
            # (Futures is "with" the strategy, CFD is "against")
            if is_win:
                f_trade_pnl = reward   # futures wins big
                c_trade_pnl = -reward  # CFD loses big
            else:
                f_trade_pnl = -risk    # futures loses small
                c_trade_pnl = risk     # CFD wins small

            # Apply commissions to live accounts
            if not f_blown:
                f_trade_pnl -= f_comm
            else:
                f_trade_pnl = 0.0

            if not c_blown:
                c_trade_pnl -= c_comm
            else:
                c_trade_pnl = 0.0

            # Update running P&L
            f_pnl += f_trade_pnl
            c_pnl += c_trade_pnl
            day_f_pnl += f_trade_pnl
            day_c_pnl += c_trade_pnl

            # Update peaks (only upward, only for live accounts)
            if not f_blown and f_pnl > f_peak:
                f_peak = f_pnl
            if not c_blown and c_pnl > c_peak:
                c_peak = c_pnl

            # Trailing DD check (STICKY — once blown, permanently blown)
            if not f_blown:
                f_dd = f_peak - f_pnl
                if f_dd >= fc["max_dd"]:
                    f_blown = True

            if not c_blown:
                c_dd = c_peak - c_pnl
                if c_dd >= cc["max_dd"]:
                    c_blown = True

            # Daily loss limit check (futures only in our presets)
            if not f_blown and fc["daily_limit"] > 0:
                if day_f_pnl <= -fc["daily_limit"]:
                    f_blown = True

            if not c_blown and cc["daily_limit"] > 0:
                if day_c_pnl <= -cc["daily_limit"]:
                    c_blown = True

            # Profit target check (only live accounts)
            if not f_blown and f_pnl >= fc["profit_target"]:
                f_passed = True
            if not c_blown and c_pnl >= cc["profit_target"]:
                c_passed = True

            # Resolution check
            if f_passed or c_passed or (f_blown and c_blown):
                resolve_day = trade_day + 1
                resolved = True
                break

        # Record outcome
        days_to_resolve.append(resolve_day)

        if f_passed:
            futures_wins += 1
            net = (f_pnl * config.payout_split) - total_cost
            profits_futures_win.append(net)
        elif c_passed:
            cfd_wins += 1
            net = (c_pnl * config.payout_split) - total_cost
            profits_cfd_win.append(net)
        elif f_blown and c_blown:
            both_blown += 1
        else:
            timeouts += 1

    # Compute rates
    f_pass_rate = futures_wins / n_sims
    c_pass_rate = cfd_wins / n_sims
    combined_wr = f_pass_rate + c_pass_rate
    blown_rate = both_blown / n_sims
    to_rate = timeouts / n_sims

    # Average profits
    avg_f_profit = (
        sum(profits_futures_win) / len(profits_futures_win)
        if profits_futures_win else 0.0
    )
    avg_c_profit = (
        sum(profits_cfd_win) / len(profits_cfd_win)
        if profits_cfd_win else 0.0
    )

    # EV calculation
    # Win: net profit after payout and fees
    # Blown: lose both challenge fees
    # Timeout: lose both challenge fees (account didn't resolve)
    ev = (
        f_pass_rate * avg_f_profit
        + c_pass_rate * avg_c_profit
        + blown_rate * (-total_cost)
        + to_rate * (-total_cost)
    )

    roi = ev / total_cost if total_cost > 0 else 0.0

    avg_days = sum(days_to_resolve) / len(days_to_resolve) if days_to_resolve else max_days

    # Break-even win rate: what combined_wr would make EV = 0?
    # At break-even: combined_wr * avg_net_profit = (1 - combined_wr) * total_cost
    # => be_wr = total_cost / (total_cost + avg_net_profit)
    avg_net_profit = 0.0
    if profits_futures_win or profits_cfd_win:
        all_profits = profits_futures_win + profits_cfd_win
        avg_net_profit = sum(all_profits) / len(all_profits)
    if avg_net_profit > 0:
        be_wr = total_cost / (total_cost + avg_net_profit)
    else:
        be_wr = 1.0

    # Monthly / annual projections
    attempts_per_month = 30 / max(avg_days, 1)
    monthly = ev * attempts_per_month
    annual = monthly * 12

    return HedgeTradeResult(
        n_sims=n_sims,
        win_rate_used=config.strategy_win_rate,
        rr_used=config.strategy_rr,
        futures_pass_rate=f_pass_rate,
        cfd_pass_rate=c_pass_rate,
        combined_win_rate=combined_wr,
        both_blown_rate=blown_rate,
        timeout_rate=to_rate,
        avg_profit_futures_win=avg_f_profit,
        avg_profit_cfd_win=avg_c_profit,
        expected_value_per_attempt=ev,
        roi_per_attempt=roi,
        avg_days_to_resolve=avg_days,
        break_even_win_rate=be_wr,
        monthly_ev=monthly,
        annual_ev=annual,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MATRIX SCAN
# ═══════════════════════════════════════════════════════════════════════════════

def generate_hedge_trade_matrix(
    futures_config: dict,
    cfd_config: dict,
    risk_per_trade: float,
    trades_per_day: float,
    payout_split: float = 0.85,
    n_sims: int = 1_000,
) -> dict:
    """
    Grid scan: WR [35%-65%] x RR [1.0-4.0].

    Returns dict with 'grid' (list of dicts) and 'summary' (formatted string).
    """
    win_rates = [round(x * 0.05 + 0.35, 2) for x in range(7)]   # 0.35 to 0.65
    rr_values = [round(x * 0.5 + 1.0, 1) for x in range(7)]     # 1.0 to 4.0

    grid: list[dict] = []

    for wr in win_rates:
        for rr in rr_values:
            cfg = HedgeTradeConfig(
                strategy_win_rate=wr,
                strategy_rr=rr,
                risk_per_trade=risk_per_trade,
                trades_per_day=trades_per_day,
                futures_config=futures_config,
                cfd_config=cfd_config,
                payout_split=payout_split,
            )
            res = simulate_hedge_trades(cfg, n_sims=n_sims, seed=42)
            grid.append({
                "win_rate": wr,
                "rr": rr,
                "edge": wr * rr - (1 - wr),  # expected R per trade
                "combined_win_rate": res.combined_win_rate,
                "ev": res.expected_value_per_attempt,
                "roi": res.roi_per_attempt,
                "monthly_ev": res.monthly_ev,
                "avg_days": res.avg_days_to_resolve,
                "futures_pass": res.futures_pass_rate,
                "cfd_pass": res.cfd_pass_rate,
                "both_blown": res.both_blown_rate,
            })

    # Build formatted summary
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 110)
    lines.append("  HEDGE TRADE MODEL — PARAMETER MATRIX")
    lines.append(f"  Risk/trade: ${risk_per_trade:.0f}  |  Trades/day: {trades_per_day:.1f}  |  "
                 f"Payout: {payout_split:.0%}  |  Sims: {n_sims:,}")
    lines.append("=" * 110)

    # Header row
    header = f"  {'WR':>5} | {'Edge':>6} |"
    for rr in rr_values:
        header += f" RR={rr:<4} |"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    # EV sub-table
    lines.append("  EV per attempt ($):")
    for wr in win_rates:
        row = f"  {wr:>5.0%} | {wr * 2.0 - (1 - wr):>+5.2f} |"  # edge at RR=2 as reference
        for rr in rr_values:
            cell = [g for g in grid if g["win_rate"] == wr and g["rr"] == rr][0]
            ev_str = f"${cell['ev']:>+7,.0f}" if abs(cell["ev"]) >= 1 else f"  {'~$0':>5}"
            row += f" {ev_str} |"
        lines.append(row)

    lines.append("")
    lines.append("  Combined win rate (%):")
    for wr in win_rates:
        row = f"  {wr:>5.0%} |        |"
        for rr in rr_values:
            cell = [g for g in grid if g["win_rate"] == wr and g["rr"] == rr][0]
            row += f" {cell['combined_win_rate']*100:>5.1f}% |"
        lines.append(row)

    lines.append("")
    lines.append("  Monthly EV ($):")
    for wr in win_rates:
        row = f"  {wr:>5.0%} |        |"
        for rr in rr_values:
            cell = [g for g in grid if g["win_rate"] == wr and g["rr"] == rr][0]
            row += f"${cell['monthly_ev']:>+7,.0f} |"
        lines.append(row)

    lines.append("")

    # Highlight best cells
    profitable = [g for g in grid if g["ev"] > 0]
    if profitable:
        best = max(profitable, key=lambda g: g["ev"])
        lines.append(f"  BEST CELL: WR={best['win_rate']:.0%} RR={best['rr']:.1f} "
                     f"-> EV=${best['ev']:+,.0f}/attempt, "
                     f"Monthly=${best['monthly_ev']:+,.0f}, "
                     f"Win%={best['combined_win_rate']*100:.1f}%")
    else:
        lines.append("  WARNING: No profitable cells found in the scanned range.")

    lines.append("=" * 110)

    summary = "\n".join(lines)

    return {
        "grid": grid,
        "win_rates": win_rates,
        "rr_values": rr_values,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT PRINTER
# ═══════════════════════════════════════════════════════════════════════════════

def print_hedge_trade_report(result: HedgeTradeResult):
    """Print a formatted report of the hedge trade simulation results."""
    att_mo = 30 / max(result.avg_days_to_resolve, 1)
    edge = result.win_rate_used * result.rr_used - (1 - result.win_rate_used)

    print(f"\n{'='*70}")
    print(f"  CROSS-ACCOUNT HEDGE — TRADE MODEL")
    print(f"  {result.n_sims:,} simulations")
    print(f"{'='*70}")
    print(f"  Strategy:  WR={result.win_rate_used:.0%}  R:R=1:{result.rr_used:.1f}  "
          f"Edge={edge:+.3f}R/trade")
    print(f"")
    print(f"  OUTCOMES:")
    print(f"    Futures passes:    {result.futures_pass_rate*100:>6.1f}%")
    print(f"    CFD passes:        {result.cfd_pass_rate*100:>6.1f}%")
    print(f"    COMBINED WIN RATE: {result.combined_win_rate*100:>6.1f}%")
    print(f"    Both blown:        {result.both_blown_rate*100:>6.1f}%")
    print(f"    Timeout:           {result.timeout_rate*100:>6.1f}%")
    print(f"")
    print(f"  ECONOMICS (after payout split):")
    print(f"    Avg profit (futures win): ${result.avg_profit_futures_win:>+,.0f}")
    print(f"    Avg profit (CFD win):     ${result.avg_profit_cfd_win:>+,.0f}")
    print(f"    EV per attempt:           ${result.expected_value_per_attempt:>+,.0f}")
    print(f"    ROI per attempt:          {result.roi_per_attempt*100:>+.0f}%")
    print(f"    Break-even win rate:      {result.break_even_win_rate*100:.1f}%")
    print(f"    Avg days to resolve:      {result.avg_days_to_resolve:.1f}")
    print(f"")
    print(f"  PROJECTIONS ({att_mo:.1f} attempts/month):")
    print(f"    Monthly EV:   ${result.monthly_ev:>+,.0f}")
    print(f"    Annual EV:    ${result.annual_ev:>+,.0f}")
    print(f"{'='*70}")
