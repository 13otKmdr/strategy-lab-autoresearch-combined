"""Emergency kill switch for the execution layer.

When activated, ALL trading is blocked — no new orders, no modifications.
The kill switch is checked at multiple points in the pipeline:
  - require_live_gates() checks it for LIVE mode
  - RiskDaemon checks it before any risk check
  - Broker adapters check it before submission

Activation reasons are logged and must be provided (no blind activations).
"""
from __future__ import annotations


class KillSwitch:
    """Emergency halt mechanism.

    Once activated, remains active until explicitly deactivated.
    All activations and deactivations should be audit-logged by the caller.
    """

    def __init__(self) -> None:
        self._active: bool = False
        self._reason: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str | None:
        return self._reason

    def activate(self, reason: str) -> None:
        self._active = True
        self._reason = reason

    def deactivate(self) -> None:
        self._active = False
        self._reason = None

    def allows_trading(self) -> bool:
        return not self._active
