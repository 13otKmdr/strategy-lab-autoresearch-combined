"""Futures-native contract specifications for prop-challenge modeling."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuturesContractSpec:
    symbol: str
    name: str
    exchange: str
    tick_size: float
    tick_value: float
    point_value: float
    contract_type: str  # "micro" | "mini"
    projectx_symbol_id: str | None = None


CONTRACT_SPECS: dict[str, FuturesContractSpec] = {
    "MYM": FuturesContractSpec(
        symbol="MYM",
        name="Micro E-mini Dow",
        exchange="CBOT",
        tick_size=1,
        tick_value=0.50,
        point_value=0.50,
        contract_type="micro",
        projectx_symbol_id="F.US.MYM",
    ),
    "YM": FuturesContractSpec(
        symbol="YM",
        name="E-mini Dow",
        exchange="CBOT",
        tick_size=1,
        tick_value=5.00,
        point_value=5.00,
        contract_type="mini",
        projectx_symbol_id="F.US.YM",
    ),
    "MES": FuturesContractSpec(
        symbol="MES",
        name="Micro E-mini S&P 500",
        exchange="CME",
        tick_size=0.25,
        tick_value=1.25,
        point_value=5.00,
        contract_type="micro",
        projectx_symbol_id="F.US.MES",
    ),
    "ES": FuturesContractSpec(
        symbol="ES",
        name="E-mini S&P 500",
        exchange="CME",
        tick_size=0.25,
        tick_value=12.50,
        point_value=50.00,
        contract_type="mini",
        projectx_symbol_id="F.US.EP",
    ),
    "MNQ": FuturesContractSpec(
        symbol="MNQ",
        name="Micro E-mini Nasdaq-100",
        exchange="CME",
        tick_size=0.25,
        tick_value=0.50,
        point_value=2.00,
        contract_type="micro",
        projectx_symbol_id="F.US.MNQ",
    ),
    "NQ": FuturesContractSpec(
        symbol="NQ",
        name="E-mini Nasdaq-100",
        exchange="CME",
        tick_size=0.25,
        tick_value=5.00,
        point_value=20.00,
        contract_type="mini",
        projectx_symbol_id="F.US.ENQ",
    ),
    "MGC": FuturesContractSpec(
        symbol="MGC",
        name="Micro Gold",
        exchange="COMEX",
        tick_size=0.10,
        tick_value=1.00,
        point_value=10.00,
        contract_type="micro",
        projectx_symbol_id="F.US.MGC",
    ),
    "GC": FuturesContractSpec(
        symbol="GC",
        name="Gold",
        exchange="COMEX",
        tick_size=0.10,
        tick_value=10.00,
        point_value=100.00,
        contract_type="mini",
        projectx_symbol_id="F.US.GCLE",
    ),
    "MCL": FuturesContractSpec(
        symbol="MCL",
        name="Micro Crude Oil",
        exchange="NYMEX",
        tick_size=0.01,
        tick_value=1.00,
        point_value=100.00,
        contract_type="micro",
        projectx_symbol_id="F.US.MCL",
    ),
    "CL": FuturesContractSpec(
        symbol="CL",
        name="Crude Oil",
        exchange="NYMEX",
        tick_size=0.01,
        tick_value=10.00,
        point_value=1000.00,
        contract_type="mini",
        projectx_symbol_id="F.US.CLE",
    ),
}


def get_contract_spec(symbol: str) -> FuturesContractSpec:
    key = symbol.upper()
    try:
        return CONTRACT_SPECS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown futures contract symbol: {symbol}") from exc


def is_micro_symbol(symbol: str) -> bool:
    return get_contract_spec(symbol).contract_type == "micro"


def is_mini_symbol(symbol: str) -> bool:
    return get_contract_spec(symbol).contract_type == "mini"


def dollars_per_contract_tick_move(symbol: str, contracts: int, ticks: int | float = 1) -> float:
    if contracts < 0:
        raise ValueError("contracts must be non-negative")
    spec = get_contract_spec(symbol)
    return float(spec.tick_value * contracts * ticks)
