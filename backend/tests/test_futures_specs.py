from app.models.futures import (
    CONTRACT_SPECS,
    get_contract_spec,
    is_micro_symbol,
    is_mini_symbol,
    dollars_per_contract_tick_move,
)


def test_mym_contract_spec_matches_projectx_contract():
    spec = get_contract_spec("MYM")

    assert spec.symbol == "MYM"
    assert spec.name == "Micro E-mini Dow"
    assert spec.tick_size == 1
    assert spec.tick_value == 0.50
    assert spec.contract_type == "micro"


def test_ym_is_classified_as_blocked_mini_contract():
    spec = get_contract_spec("YM")

    assert spec.contract_type == "mini"
    assert is_mini_symbol("YM") is True
    assert is_micro_symbol("YM") is False


def test_mym_is_micro_symbol():
    assert is_micro_symbol("MYM") is True
    assert is_mini_symbol("MYM") is False


def test_dollars_per_tick_move_uses_tick_value_and_contract_count():
    assert dollars_per_contract_tick_move("MYM", contracts=3, ticks=10) == 15.0


def test_contract_specs_include_blocked_high_volatility_mnq():
    assert "MNQ" in CONTRACT_SPECS
    assert get_contract_spec("MNQ").contract_type == "micro"
