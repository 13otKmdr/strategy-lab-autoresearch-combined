"""Research profile helpers for challenge-focused strategy generation."""
from __future__ import annotations


CHALLENGE_PROFILES = {"prop_done_right_tdg", "topstep_mym_challenge"}
BROAD_RESEARCH_PROFILES = {"broad_research", "all", "research"}


def _normalise_symbols(symbols) -> tuple[str, ...]:
    if isinstance(symbols, str):
        raw = symbols.split(",")
    else:
        raw = list(symbols or [])
    return tuple(s.strip().upper() for s in raw if str(s).strip())


def select_instruments(
    all_symbols: list[str] | tuple[str, ...],
    profile: str,
    allowed_symbols: list[str] | tuple[str, ...] | str = ("MYM",),
    blocked_symbols: list[str] | tuple[str, ...] | str = ("MNQ", "NQ", "ES", "YM", "RTY"),
) -> list[str]:
    """Select research instruments for the active prop profile.

    Challenge profiles fail closed to an explicit allowlist. Broad research
    profiles retain all symbols except blocked symbols. Unknown profiles use
    challenge behavior because this system should not accidentally broaden risk.
    """
    profile_key = (profile or "prop_done_right_tdg").strip().lower()
    available = [s.upper() for s in all_symbols]
    allowed = set(_normalise_symbols(allowed_symbols))
    blocked = set(_normalise_symbols(blocked_symbols))

    if profile_key in BROAD_RESEARCH_PROFILES:
        selected = [symbol for symbol in available if symbol not in blocked]
    else:
        selected = [symbol for symbol in available if symbol in allowed and symbol not in blocked]

    if not selected:
        raise ValueError(
            f"No instruments enabled for profile {profile_key!r}; available={available}, allowed={sorted(allowed)}, blocked={sorted(blocked)}"
        )
    return selected
