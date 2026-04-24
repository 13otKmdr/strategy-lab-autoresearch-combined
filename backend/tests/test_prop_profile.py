from app.engine.prop_profile import select_instruments


def test_prop_done_right_profile_defaults_to_mym_only():
    selected = select_instruments(
        all_symbols=["MES", "MNQ", "MYM", "MGC"],
        profile="prop_done_right_tdg",
        allowed_symbols=("MYM",),
        blocked_symbols=("MNQ", "NQ", "ES", "YM", "RTY"),
    )

    assert selected == ["MYM"]


def test_broad_research_profile_keeps_all_non_blocked_symbols():
    selected = select_instruments(
        all_symbols=["MES", "MNQ", "MYM", "MGC"],
        profile="broad_research",
        allowed_symbols=("MYM",),
        blocked_symbols=("MNQ",),
    )

    assert selected == ["MES", "MYM", "MGC"]


def test_custom_allowed_symbols_are_respected_for_challenge_profile():
    selected = select_instruments(
        all_symbols=["MES", "MNQ", "MYM", "MGC"],
        profile="prop_done_right_tdg",
        allowed_symbols=("MYM", "MES"),
        blocked_symbols=("MNQ",),
    )

    assert selected == ["MES", "MYM"]


def test_empty_selection_fails_closed():
    try:
        select_instruments(
            all_symbols=["MES", "MNQ"],
            profile="prop_done_right_tdg",
            allowed_symbols=("MYM",),
            blocked_symbols=("MNQ",),
        )
    except ValueError as exc:
        assert "No instruments enabled" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty instrument selection")
