"""Order lifecycle state machine.

Valid transitions:
  PENDING   → SUBMITTED | CANCELLED | REJECTED
  SUBMITTED → ACCEPTED | REJECTED | CANCELLED
  ACCEPTED  → FILLED | CANCELLED
  FILLED    → (terminal)
  CANCELLED → (terminal)
  REJECTED  → (terminal)

Any transition not in this graph raises ValueError.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.execution.trade_intent import TradeIntent


class OrderState(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# Allowed transitions: from_state → set of to_states
_VALID_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PENDING: {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACCEPTED, OrderState.REJECTED, OrderState.CANCELLED},
    OrderState.ACCEPTED: {OrderState.FILLED, OrderState.CANCELLED},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}


@dataclass
class Order:
    """A tracked order in the state machine."""
    order_id: str
    intent: TradeIntent
    state: OrderState = OrderState.PENDING


class OrderStateMachine:
    """Manages order lifecycle transitions.

    Every transition is validated against the allowed graph.
    Invalid transitions raise ValueError to prevent corrupt state.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def create_order(self, order_id: str, intent: TradeIntent) -> Order:
        order = Order(order_id=order_id, intent=intent, state=OrderState.PENDING)
        self._orders[order_id] = order
        return order

    def transition(self, order: Order, new_state: OrderState) -> None:
        allowed = _VALID_TRANSITIONS.get(order.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"invalid transition: {order.state.value} → {new_state.value} "
                f"(order {order.order_id})"
            )
        order.state = new_state

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)
