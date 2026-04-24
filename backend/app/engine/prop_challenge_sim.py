"""Prop challenge path simulator for backtest trade lists.

This wrapper evaluates closed backtest trades against the stricter Prop Done
Right / TDG operating rules and Topstep Trading Combine path mechanics. It is
broker-neutral and intentionally has no live trading or ProjectX dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

try:  # pragma: no cover - exercised implicitly when zoneinfo data is present.
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python always has zoneinfo in supported envs.
    ZoneInfo = None  # type: ignore[assignment]

from app.engine.prop_done_right import PropDoneRightConfig
from app.engine.topstep_rules import TopstepCombineRules, TopstepPathState
from app.models.backtest import Trade


@dataclass(frozen=True)
class PropChallengeResult:
    outcome: str
    reason: str
    total_profit: float
    days_traded: int
    best_day_profit: float
    consistency_passed: bool
    mll_breached: bool
    daily_lockouts: int
    profit_lockouts: int
    trades_taken: int
    trades_skipped: int
    mll_floor_path: list[float]
    day_pnls: dict[str, float]


def _central_tz():
    if ZoneInfo is None:
        return timezone(timedelta(hours=-6), name="Central")
    try:
        return ZoneInfo("America/Chicago")
    except Exception:
        return timezone(timedelta(hours=-6), name="Central")


def _trade_datetime_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(_central_tz())


def _trading_day_key(timestamp_ms: int) -> str:
    """Return the Central Time futures trading-day key for a timestamp.

    Topstep futures sessions commonly roll at 5:00 PM Central. A trade opened
    at or after 17:00 CT is assigned to the next calendar trading day. If the
    system cannot load IANA timezone data, a fixed Central offset fallback is
    used cleanly.
    """
    local_dt = _trade_datetime_ms(timestamp_ms)
    if local_dt.hour >= 17:
        local_dt = local_dt + timedelta(days=1)
    return local_dt.date().isoformat()


def _sorted_trades(trades: Iterable[Trade]) -> list[Trade]:
    return sorted(trades, key=lambda trade: (trade.entry_ts, trade.exit_ts, trade.entry_bar))


def _best_day_profit(day_pnls: dict[str, float]) -> float:
    return max([0.0, *day_pnls.values()])


def _daily_loss_lockout_reason(day: str, day_pnl: float, rules: TopstepCombineRules, config: PropDoneRightConfig) -> str | None:
    """Return a lockout reason if either TDG DRB or Topstep DLL is breached."""
    if day_pnl <= -config.daily_risk_budget:
        return f"Daily Risk Budget lockout on {day} at ${day_pnl:.2f}"
    if rules.daily_loss_limit is not None and day_pnl <= -rules.daily_loss_limit:
        return f"Topstep Daily Loss Limit lockout on {day} at ${day_pnl:.2f}"
    return None


def simulate_prop_challenge(
    trades: list[Trade],
    topstep_rules: TopstepCombineRules | None = None,
    prop_config: PropDoneRightConfig | None = None,
    max_trades_per_day: int = 3,
    target_sessions: int = 25,
) -> PropChallengeResult:
    """Simulate a Topstep/Prop Done Right challenge path from closed trades.

    The simulator applies entry lockouts before each trade based on the current
    Central Time trading day net P&L, then updates realized Topstep equity after
    accepted trades. The Maximum Loss Limit is checked after every accepted
    trade and the trailing floor is advanced at each end-of-day balance update.

    Outcomes:
    - ``pass``: profit target reached and Topstep consistency is satisfied.
    - ``fail_mll``: realized equity breached the Topstep MLL floor.
    - ``fail_consistency``: target reached, but best-day concentration failed.
    - ``timeout``: trade list ended before a passing result or hard failure.
    """
    rules = topstep_rules or TopstepCombineRules.topstep_50k()
    config = prop_config or PropDoneRightConfig(official_mll_amount=rules.maximum_loss_limit)
    if max_trades_per_day < 1:
        raise ValueError("max_trades_per_day must be at least 1")
    if target_sessions < 1:
        raise ValueError("target_sessions must be at least 1")

    path_state = TopstepPathState(rules)
    mll_floor_path: list[float] = [path_state.mll_floor]
    day_pnls: dict[str, float] = {}
    day_trade_counts: dict[str, int] = {}
    traded_days: set[str] = set()

    total_profit = 0.0
    trades_taken = 0
    trades_skipped = 0
    daily_lockout_days: set[str] = set()
    profit_lockout_days: set[str] = set()
    max_trade_skips = 0
    last_lockout_reason = ""
    mll_breached = False
    current_day: str | None = None

    def make_result(outcome: str, reason: str) -> PropChallengeResult:
        best_day = _best_day_profit(day_pnls)
        return PropChallengeResult(
            outcome=outcome,
            reason=reason,
            total_profit=total_profit,
            days_traded=len(traded_days),
            best_day_profit=best_day,
            consistency_passed=rules.consistency_passes(total_profit, best_day),
            mll_breached=mll_breached,
            daily_lockouts=len(daily_lockout_days),
            profit_lockouts=len(profit_lockout_days),
            trades_taken=trades_taken,
            trades_skipped=trades_skipped,
            mll_floor_path=list(mll_floor_path),
            day_pnls=dict(day_pnls),
        )

    def finalise_day() -> PropChallengeResult | None:
        balance = rules.account_size + total_profit
        path_state.apply_end_of_day_balance(balance)
        mll_floor_path.append(path_state.mll_floor)

        best_day = _best_day_profit(day_pnls)
        if (
            len(traded_days) >= rules.min_trading_days
            and total_profit >= rules.profit_target
            and rules.consistency_passes(total_profit, best_day)
        ):
            return make_result("pass", "profit target reached with Topstep consistency satisfied")
        return None

    for trade in _sorted_trades(trades):
        trade_day = _trading_day_key(trade.entry_ts)
        if current_day is None:
            current_day = trade_day
        elif trade_day != current_day:
            pass_result = finalise_day()
            if pass_result is not None:
                return pass_result
            current_day = trade_day

        day_pnl = day_pnls.get(trade_day, 0.0)
        daily_loss_reason = _daily_loss_lockout_reason(trade_day, day_pnl, rules, config)
        if daily_loss_reason is not None:
            trades_skipped += 1
            daily_lockout_days.add(trade_day)
            last_lockout_reason = daily_loss_reason
            continue

        if day_pnl >= config.power_quitting_hard_profit:
            trades_skipped += 1
            profit_lockout_days.add(trade_day)
            last_lockout_reason = f"Power of Quitting lockout on {trade_day} at ${day_pnl:.2f}"
            continue

        if day_trade_counts.get(trade_day, 0) >= max_trades_per_day:
            trades_skipped += 1
            max_trade_skips += 1
            last_lockout_reason = f"max trades/day lockout on {trade_day}: {max_trades_per_day} trades already taken"
            continue

        pnl = float(trade.pnl)
        total_profit += pnl
        new_day_pnl = day_pnl + pnl
        day_pnls[trade_day] = new_day_pnl
        day_trade_counts[trade_day] = day_trade_counts.get(trade_day, 0) + 1
        traded_days.add(trade_day)
        trades_taken += 1

        daily_loss_reason = _daily_loss_lockout_reason(trade_day, new_day_pnl, rules, config)
        if daily_loss_reason is not None:
            daily_lockout_days.add(trade_day)
            last_lockout_reason = daily_loss_reason
        elif new_day_pnl >= config.power_quitting_hard_profit:
            profit_lockout_days.add(trade_day)
            last_lockout_reason = f"Power of Quitting lockout on {trade_day} at ${new_day_pnl:.2f}"

        mll_floor_path.append(path_state.mll_floor)
        if path_state.is_mll_breached(realized_pnl=total_profit):
            mll_breached = True
            return make_result(
                "fail_mll",
                f"Maximum Loss Limit breached: equity ${rules.account_size + total_profit:.2f} <= floor ${path_state.mll_floor:.2f}",
            )

    if current_day is not None and not mll_breached:
        pass_result = finalise_day()
        if pass_result is not None:
            return pass_result

    best_day = _best_day_profit(day_pnls)
    if total_profit >= rules.profit_target and not rules.consistency_passes(total_profit, best_day):
        session_note = ""
        if len(traded_days) < target_sessions:
            session_note = f" after only {len(traded_days)} session(s); target pass horizon is {target_sessions} sessions"
        return make_result(
            "fail_consistency",
            f"profit target reached{session_note}, but Topstep consistency failed: best day ${best_day:.2f} is at least 50% of total profit ${total_profit:.2f}",
        )

    if trades_skipped and last_lockout_reason:
        reason = f"trade list ended before profit target; last lockout: {last_lockout_reason}"
    elif max_trade_skips:
        reason = "trade list ended before profit target after max trades/day skips"
    elif trades_taken == 0:
        reason = "no trades taken"
    else:
        reason = "trade list ended before profit target"

    return make_result("timeout", reason)
