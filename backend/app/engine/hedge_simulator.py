"""
Cross-Account Hedge Simulator v2 (Bug-fixed + Scaling Model).

FIXES from quant review:
- Sticky DD: once an account hits DD limit, it's permanently blown (no recovery)
- Frozen P&L: blown account's position size set to 0, no phantom P&L
- Payout split: configurable (default 85%)

ADDITIONS:
- Funded account hedge simulation (post-challenge)
- Scaling model: 3 initial pairs → reinvest profits → compound growth
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.models.market import Candle
from app.engine.indicators import atr


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT CONFIGS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PropFirmAccount:
    name: str
    account_type: str
    account_size: float
    challenge_cost: float
    profit_target: float
    max_drawdown: float
    target_max_dd: float
    daily_loss_limit: float
    commission_per_trade: float
    slippage_pct: float
    payout_split: float = 0.85  # firm keeps 15%, you get 85%


FUTURES_50K = PropFirmAccount(
    name="Futures 50K (1-step)",
    account_type="futures",
    account_size=50_000,
    challenge_cost=70,
    profit_target=3_000,
    max_drawdown=2_000,
    target_max_dd=2_000,
    daily_loss_limit=1_000,
    commission_per_trade=5.0,
    slippage_pct=0.001,
    payout_split=0.85,
)

CFD_50K = PropFirmAccount(
    name="CFD 50K (Funded Hive style)",
    account_type="cfd",
    account_size=50_000,
    challenge_cost=75,
    profit_target=5_000,
    max_drawdown=5_000,
    target_max_dd=3_000,
    daily_loss_limit=0,
    commission_per_trade=3.0,
    slippage_pct=0.0015,
    payout_split=0.85,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HedgeSimResult:
    n_sims: int
    futures_account: str
    cfd_account: str
    total_challenge_cost: float
    payout_split: float

    futures_wins_pct: float
    cfd_wins_pct: float
    both_blown_pct: float
    timeout_pct: float

    avg_profit_when_futures_wins: float  # AFTER payout split and fees
    avg_profit_when_cfd_wins: float
    avg_loss_when_both_blown: float
    expected_value_per_attempt: float
    avg_days_to_resolve: float

    net_ev_per_attempt: float
    roi_per_attempt: float
    break_even_win_rate: float

    worst_case_loss: float
    best_case_profit: float

    futures_avg_pnl: float
    cfd_avg_pnl: float
    avg_trades_per_sim: int


@dataclass
class ScalingModelResult:
    initial_pairs: int
    initial_investment: float
    months: list[dict]
    total_profit: float
    total_challenges_bought: int
    total_funded_accounts: int
    total_challenge_cost: float
    final_monthly_income: float


# ═══════════════════════════════════════════════════════════════════════════════
# CORE HEDGE SIMULATOR (BUG-FIXED)
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_hedge(
    candles: list[Candle],
    futures_config: PropFirmAccount = FUTURES_50K,
    cfd_config: PropFirmAccount = CFD_50K,
    risk_pct: float = 1.0,
    n_sims: int = 5000,
    max_days: int = 30,
    seed: int = 42,
) -> HedgeSimResult:
    n = len(candles)
    if n < 500:
        raise ValueError("Need at least 500 candles")

    close = np.array([c.close for c in candles])
    high_arr = np.array([c.high for c in candles])
    low_arr = np.array([c.low for c in candles])
    atr_arr = atr(high_arr, low_arr, close, 14)

    rng = np.random.default_rng(seed)
    bars_per_day = 7

    total_cost = futures_config.challenge_cost + cfd_config.challenge_cost
    payout = futures_config.payout_split  # assume same for both

    futures_wins = 0
    cfd_wins = 0
    both_blown = 0
    timeouts = 0

    profits_futures_wins = []
    profits_cfd_wins = []
    losses_both_blown = []
    all_days = []
    all_futures_pnl = []
    all_cfd_pnl = []
    all_trades = []

    for sim in range(n_sims):
        max_start = n - (max_days * bars_per_day) - 10
        if max_start < 200:
            max_start = 200
        start_idx = rng.integers(200, max(201, max_start))

        futures_long = rng.random() > 0.5

        f_equity = futures_config.account_size
        c_equity = cfd_config.account_size
        f_peak = f_equity
        c_peak = c_equity
        f_pnl = 0.0
        c_pnl = 0.0

        a = atr_arr[start_idx]
        if math.isnan(a) or a <= 0:
            a = close[start_idx] * 0.01

        f_risk_usd = f_equity * (risk_pct / 100)
        c_risk_usd = c_equity * (risk_pct / 100)
        f_size = f_risk_usd / a
        c_size = c_risk_usd / a

        # STICKY FLAGS — once blown, permanently blown
        f_is_blown = False
        c_is_blown = False
        f_passed = False
        c_passed = False

        bars_traded = 0
        trade_count = 0
        daily_f_pnl = 0.0
        daily_c_pnl = 0.0

        for i in range(start_idx + 1, min(start_idx + max_days * bars_per_day, n)):
            bars_traded += 1
            price_change = close[i] - close[i - 1]

            # P&L only for LIVE accounts (frozen if blown)
            if futures_long:
                f_bar_pnl = price_change * f_size if not f_is_blown else 0
                c_bar_pnl = -price_change * c_size if not c_is_blown else 0
            else:
                f_bar_pnl = -price_change * f_size if not f_is_blown else 0
                c_bar_pnl = price_change * c_size if not c_is_blown else 0

            # Slippage on live accounts only
            if not f_is_blown:
                f_bar_pnl -= abs(f_bar_pnl) * futures_config.slippage_pct
            if not c_is_blown:
                c_bar_pnl -= abs(c_bar_pnl) * cfd_config.slippage_pct

            if bars_traded % bars_per_day == 1:
                if not f_is_blown:
                    f_bar_pnl -= futures_config.commission_per_trade
                if not c_is_blown:
                    c_bar_pnl -= cfd_config.commission_per_trade
                daily_f_pnl = 0
                daily_c_pnl = 0
                trade_count += 1

            f_equity += f_bar_pnl
            c_equity += c_bar_pnl
            f_pnl += f_bar_pnl
            c_pnl += c_bar_pnl
            daily_f_pnl += f_bar_pnl
            daily_c_pnl += c_bar_pnl

            # Update peaks for live accounts only
            if not f_is_blown and f_equity > f_peak:
                f_peak = f_equity
            if not c_is_blown and c_equity > c_peak:
                c_peak = c_equity

            # Trailing DD
            f_dd = f_peak - f_equity
            c_dd = c_peak - c_equity

            # STICKY DD CHECK — once blown, stays blown
            if not f_is_blown:
                if f_dd >= futures_config.max_drawdown:
                    f_is_blown = True
                    f_size = 0  # freeze position
                if futures_config.daily_loss_limit > 0 and daily_f_pnl < 0 and abs(daily_f_pnl) >= futures_config.daily_loss_limit:
                    f_is_blown = True
                    f_size = 0

            if not c_is_blown:
                if c_dd >= cfd_config.target_max_dd:
                    c_is_blown = True
                    c_size = 0

            # Check passes (on live accounts)
            if not f_is_blown and f_pnl >= futures_config.profit_target:
                f_passed = True
            if not c_is_blown and c_pnl >= cfd_config.profit_target:
                c_passed = True

            # Resolve
            if f_passed:
                break
            if c_passed:
                break
            if f_is_blown and c_is_blown:
                break

        # Record outcome
        days = max(1, bars_traded // bars_per_day)
        all_days.append(days)
        all_futures_pnl.append(f_pnl)
        all_cfd_pnl.append(c_pnl)
        all_trades.append(trade_count)

        if f_passed:
            futures_wins += 1
            # Profit = payout_split × profit - both challenge fees
            net = (f_pnl * payout) - total_cost
            profits_futures_wins.append(net)
        elif c_passed:
            cfd_wins += 1
            net = (c_pnl * payout) - total_cost
            profits_cfd_wins.append(net)
        elif f_is_blown and c_is_blown:
            both_blown += 1
            losses_both_blown.append(-total_cost)
        else:
            timeouts += 1

    total = n_sims
    f_win_pct = futures_wins / total
    c_win_pct = cfd_wins / total
    blown_pct = both_blown / total
    to_pct = timeouts / total

    avg_f_profit = sum(profits_futures_wins) / len(profits_futures_wins) if profits_futures_wins else 0
    avg_c_profit = sum(profits_cfd_wins) / len(profits_cfd_wins) if profits_cfd_wins else 0
    avg_blown_loss = -total_cost

    ev = (f_win_pct * avg_f_profit +
          c_win_pct * avg_c_profit +
          blown_pct * avg_blown_loss +
          to_pct * (-total_cost * 0.5))

    avg_win = (avg_f_profit + avg_c_profit) / 2 if (avg_f_profit + avg_c_profit) > 0 else 1
    be_wr = total_cost / (total_cost + avg_win) if avg_win > 0 else 1.0

    best_profit = max(
        futures_config.profit_target * payout - total_cost,
        cfd_config.profit_target * payout - total_cost,
    )

    return HedgeSimResult(
        n_sims=n_sims,
        futures_account=futures_config.name,
        cfd_account=cfd_config.name,
        total_challenge_cost=total_cost,
        payout_split=payout,
        futures_wins_pct=f_win_pct,
        cfd_wins_pct=c_win_pct,
        both_blown_pct=blown_pct,
        timeout_pct=to_pct,
        avg_profit_when_futures_wins=avg_f_profit,
        avg_profit_when_cfd_wins=avg_c_profit,
        avg_loss_when_both_blown=avg_blown_loss,
        expected_value_per_attempt=ev,
        avg_days_to_resolve=sum(all_days) / len(all_days),
        net_ev_per_attempt=ev,
        roi_per_attempt=ev / total_cost if total_cost > 0 else 0,
        break_even_win_rate=be_wr,
        worst_case_loss=-total_cost,
        best_case_profit=best_profit,
        futures_avg_pnl=sum(all_futures_pnl) / len(all_futures_pnl),
        cfd_avg_pnl=sum(all_cfd_pnl) / len(all_cfd_pnl),
        avg_trades_per_sim=int(sum(all_trades) / len(all_trades)),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCALING MODEL
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_scaling(
    hedge_result: HedgeSimResult,
    initial_pairs: int = 3,
    months_to_simulate: int = 12,
    reinvest_pct: float = 0.50,       # % of profit reinvested into more challenges
    funded_monthly_profit: float = 500, # conservative profit per funded account per month
    funded_survival_rate: float = 0.70, # % chance funded account survives each month
    max_concurrent_pairs: int = 20,
) -> ScalingModelResult:
    """
    Simulate the scaling business model month by month.

    Flow:
    1. Start with N challenge pairs
    2. Some pass → get funded accounts
    3. Use 1 funded futures + 1 funded CFD for hedge trading
    4. Funded accounts generate monthly profit (at payout split)
    5. Reinvest portion of profit into new challenge pairs
    6. Repeat, compounding
    """
    challenge_cost_per_pair = hedge_result.total_challenge_cost  # $145
    win_rate = hedge_result.futures_wins_pct + hedge_result.cfd_wins_pct
    avg_days = hedge_result.avg_days_to_resolve
    avg_profit_per_win = (
        hedge_result.avg_profit_when_futures_wins * hedge_result.futures_wins_pct +
        hedge_result.avg_profit_when_cfd_wins * hedge_result.cfd_wins_pct
    ) / max(win_rate, 0.01)
    payout = hedge_result.payout_split

    # Track state
    bankroll = initial_pairs * challenge_cost_per_pair
    initial_investment = bankroll
    funded_futures_accounts = 0
    funded_cfd_accounts = 0
    total_profit = 0
    total_challenges = initial_pairs
    total_funded = 0
    total_challenge_spend = initial_pairs * challenge_cost_per_pair

    months = []
    pending_pairs = initial_pairs

    for month in range(1, months_to_simulate + 1):
        month_data = {
            "month": month,
            "starting_bankroll": round(bankroll, 2),
            "pairs_running": pending_pairs,
        }

        # Phase 1: Resolve challenge pairs
        rounds_this_month = max(1, int(30 / max(avg_days, 1)))
        new_funded_f = 0
        new_funded_c = 0
        month_challenge_profit = 0
        month_challenge_cost = 0

        for round_num in range(rounds_this_month):
            pairs_this_round = min(pending_pairs, max_concurrent_pairs)
            if pairs_this_round <= 0:
                break

            month_challenge_cost += pairs_this_round * challenge_cost_per_pair

            for p in range(pairs_this_round):
                roll = np.random.random()
                if roll < hedge_result.futures_wins_pct:
                    # Futures passes
                    new_funded_f += 1
                    profit = avg_profit_per_win
                    month_challenge_profit += profit
                elif roll < win_rate:
                    # CFD passes
                    new_funded_c += 1
                    profit = avg_profit_per_win
                    month_challenge_profit += profit
                else:
                    # Both blown or timeout — lose fee
                    month_challenge_profit -= challenge_cost_per_pair

            # Prepare next round's pairs from reinvestment
            if month_challenge_profit > 0:
                reinvest = month_challenge_profit * reinvest_pct
                pending_pairs = max(1, int(reinvest / challenge_cost_per_pair))
            else:
                pending_pairs = max(1, pending_pairs // 2)

        funded_futures_accounts += new_funded_f
        funded_cfd_accounts += new_funded_c
        total_funded += new_funded_f + new_funded_c
        total_challenges += sum(1 for _ in range(rounds_this_month)) * pending_pairs

        # Phase 2: Funded account income
        # Pair up funded accounts: min(futures, cfd) pairs for hedge trading
        funded_pairs = min(funded_futures_accounts, funded_cfd_accounts)
        unpaired = abs(funded_futures_accounts - funded_cfd_accounts)

        # Funded pairs generate income
        month_funded_income = funded_pairs * funded_monthly_profit * 2  # both sides active
        month_funded_income += unpaired * funded_monthly_profit * 0.5   # unpaired = single strategy, less reliable

        # Apply funded survival rate (some funded accounts blow each month)
        blown_f = 0
        blown_c = 0
        for _ in range(funded_futures_accounts):
            if np.random.random() > funded_survival_rate:
                blown_f += 1
        for _ in range(funded_cfd_accounts):
            if np.random.random() > funded_survival_rate:
                blown_c += 1
        funded_futures_accounts -= blown_f
        funded_cfd_accounts -= blown_c

        # Total month income
        month_total = month_challenge_profit + month_funded_income
        total_profit += month_total
        bankroll += month_total
        total_challenge_spend += month_challenge_cost

        # Reinvest for next month
        if month_total > 0:
            reinvest_amount = month_total * reinvest_pct
            pending_pairs = max(3, int(reinvest_amount / challenge_cost_per_pair))
            pending_pairs = min(pending_pairs, max_concurrent_pairs)
        else:
            pending_pairs = max(1, pending_pairs)

        month_data.update({
            "challenge_pairs_resolved": rounds_this_month * pending_pairs,
            "new_funded_futures": new_funded_f,
            "new_funded_cfd": new_funded_c,
            "funded_blown": blown_f + blown_c,
            "active_funded_futures": funded_futures_accounts,
            "active_funded_cfd": funded_cfd_accounts,
            "funded_pairs_trading": min(funded_futures_accounts, funded_cfd_accounts),
            "challenge_profit": round(month_challenge_profit, 2),
            "funded_income": round(month_funded_income, 2),
            "total_month_income": round(month_total, 2),
            "cumulative_profit": round(total_profit, 2),
            "ending_bankroll": round(bankroll, 2),
            "next_month_pairs": pending_pairs,
            "challenge_cost_this_month": round(month_challenge_cost, 2),
        })
        months.append(month_data)

    return ScalingModelResult(
        initial_pairs=initial_pairs,
        initial_investment=initial_investment,
        months=months,
        total_profit=total_profit,
        total_challenges_bought=total_challenges,
        total_funded_accounts=total_funded,
        total_challenge_cost=total_challenge_spend,
        final_monthly_income=months[-1]["total_month_income"] if months else 0,
    )


def print_scaling_report(result: ScalingModelResult):
    print(f"\n{'='*140}")
    print(f"  SCALING MODEL — {result.initial_pairs} Initial Pairs → 12 Month Projection")
    print(f"  Initial Investment: ${result.initial_investment:,.0f}")
    print(f"{'='*140}")
    print(f"  {'Mo':<4} {'Pairs':<6} {'NewFutF':<8} {'NewCFDF':<8} {'Blown':<7} {'ActvFut':<8} {'ActvCFD':<8} {'FundPrs':<8} "
          f"{'ChallProf':<11} {'FundInc':<10} {'MonthTot':<11} {'Cumul':<12} {'Bankroll':<12} {'NextPrs':<8} {'ChallCost'}")
    print(f"  {'-'*137}")
    for m in result.months:
        print(f"  {m['month']:<4} {m['pairs_running']:<6} {m['new_funded_futures']:<8} {m['new_funded_cfd']:<8} "
              f"{m['funded_blown']:<7} {m['active_funded_futures']:<8} {m['active_funded_cfd']:<8} "
              f"{m['funded_pairs_trading']:<8} ${m['challenge_profit']:<+10,.0f} ${m['funded_income']:<9,.0f} "
              f"${m['total_month_income']:<+10,.0f} ${m['cumulative_profit']:<+11,.0f} "
              f"${m['ending_bankroll']:<11,.0f} {m['next_month_pairs']:<8} ${m['challenge_cost_this_month']:,.0f}")

    print(f"\n  TOTALS:")
    print(f"    Initial investment:     ${result.initial_investment:,.0f}")
    print(f"    Total challenge spend:  ${result.total_challenge_cost:,.0f}")
    print(f"    Total funded accounts:  {result.total_funded_accounts}")
    print(f"    Total profit (12mo):    ${result.total_profit:+,.0f}")
    print(f"    ROI on initial:         {result.total_profit / result.initial_investment * 100:+,.0f}%")
    print(f"    Final monthly income:   ${result.final_monthly_income:+,.0f}/month")


def print_hedge_report(result: HedgeSimResult):
    wr = result.futures_wins_pct + result.cfd_wins_pct
    att_mo = 30 / max(result.avg_days_to_resolve, 1)

    print(f"\n{'='*70}")
    print(f"  CROSS-ACCOUNT HEDGE — CORRECTED (Sticky DD + {result.payout_split:.0%} Payout)")
    print(f"  {result.n_sims:,} simulations")
    print(f"{'='*70}")
    print(f"  Futures: {result.futures_account}")
    print(f"  CFD:     {result.cfd_account}")
    print(f"  Cost:    ${result.total_challenge_cost:.0f} per attempt")
    print(f"  Payout:  {result.payout_split:.0%}")
    print(f"")
    print(f"  OUTCOMES:")
    print(f"    Futures passes:    {result.futures_wins_pct*100:>5.1f}%")
    print(f"    CFD passes:        {result.cfd_wins_pct*100:>5.1f}%")
    print(f"    COMBINED WIN RATE: {wr*100:>5.1f}%")
    print(f"    Both blown:        {result.both_blown_pct*100:>5.1f}%")
    print(f"    Timeout:           {result.timeout_pct*100:>5.1f}%")
    print(f"")
    print(f"  ECONOMICS (after {result.payout_split:.0%} payout split):")
    print(f"    Profit when futures wins: ${result.avg_profit_when_futures_wins:>+,.0f}")
    print(f"    Profit when CFD wins:     ${result.avg_profit_when_cfd_wins:>+,.0f}")
    print(f"    Loss when both blown:     ${result.avg_loss_when_both_blown:>+,.0f}")
    print(f"    EV per attempt:           ${result.net_ev_per_attempt:>+,.0f}")
    print(f"    ROI per attempt:          {result.roi_per_attempt*100:>+.0f}%")
    print(f"    Break-even win rate:      {result.break_even_win_rate*100:.1f}%")
    print(f"    Risk/Reward:              1:{abs(result.best_case_profit / result.worst_case_loss):.1f}")
    print(f"    Avg days to resolve:      {result.avg_days_to_resolve:.1f}")
    print(f"")
    mo_profit = result.net_ev_per_attempt * att_mo
    print(f"  MONTHLY ({att_mo:.1f} attempts):")
    print(f"    Challenge costs:  ${result.total_challenge_cost * att_mo:>,.0f}")
    print(f"    Net profit:       ${mo_profit:>+,.0f}")
    print(f"    Annual:           ${mo_profit * 12:>+,.0f}")
