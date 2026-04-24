from app.engine.topstep_rules import TopstepCombineRules, TopstepDay, TopstepPathState


def test_50k_combine_initial_mll_floor_is_48000():
    rules = TopstepCombineRules.topstep_50k()

    assert rules.initial_mll_floor == 48000


def test_mll_trails_highest_end_of_day_balance_and_never_moves_down():
    rules = TopstepCombineRules.topstep_50k()
    state = TopstepPathState(rules)

    state.apply_end_of_day_balance(50500)
    assert state.mll_floor == 48500

    state.apply_end_of_day_balance(50000)
    assert state.mll_floor == 48500


def test_mll_locks_at_starting_balance_once_high_enough():
    rules = TopstepCombineRules.topstep_50k()
    state = TopstepPathState(rules)

    state.apply_end_of_day_balance(52000)

    assert state.mll_floor == 50000


def test_intraday_unrealized_loss_can_breach_mll():
    rules = TopstepCombineRules.topstep_50k()
    state = TopstepPathState(rules)

    assert state.is_mll_breached(realized_pnl=-1500, unrealized_pnl=-501, fees=0) is True
    assert state.is_mll_breached(realized_pnl=-1500, unrealized_pnl=-499, fees=0) is False


def test_consistency_fails_when_best_day_is_at_least_half_of_total_profit():
    rules = TopstepCombineRules.topstep_50k()

    assert rules.consistency_passes(total_profit=3000, best_day_profit=1500) is False
    assert rules.consistency_passes(total_profit=3000, best_day_profit=1499) is True


def test_pass_requires_target_and_consistency():
    rules = TopstepCombineRules.topstep_50k()

    steady_days = [TopstepDay(net_profit=600) for _ in range(5)]
    one_big_day = [TopstepDay(net_profit=1500), TopstepDay(net_profit=1500)]

    assert rules.challenge_passes(steady_days) is True
    assert rules.challenge_passes(one_big_day) is False
