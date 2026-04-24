"""ProjectX / TopstepX API client for live trading and market data.

This is the REAL adapter — it makes HTTP calls to the TopstepX API.
All calls go through the safety gates in execution_mode.py before any order placement.

API Reference:
  Auth:       POST /api/Auth/loginKey
  Account:    POST /api/Account/search
  Positions:  POST /api/Position/searchOpen
  Orders:     POST /api/Order/place
  History:    POST /api/History/retrieveBars

Authentication:
  - Uses JWT session tokens obtained via /api/Auth/loginKey
  - userName field must be the account EMAIL (not the platform username)
  - Token is passed as Bearer token in Authorization header

Safety:
  - This module is a TRANSPORT layer only
  - The execution_mode gates, risk_daemon, and kill_switch sit ABOVE this
  - Never call projectx_submit_order() directly — always go through the pipeline
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum

import httpx

logger = logging.getLogger(__name__)

# ── TopstepX / ProjectX API Constants ────────────────────────────────────────

class OrderType(IntEnum):
    LIMIT = 1
    MARKET = 2
    STOP = 4
    TRAILING_STOP = 5
    JOIN_BID = 6
    JOIN_ASK = 7


class OrderSide(IntEnum):
    BUY = 0   # "Bid" in ProjectX terms
    SELL = 1  # "Ask" in ProjectX terms


class TimeframeUnit(IntEnum):
    SECOND = 1
    MINUTE = 2
    HOUR = 3
    DAY = 4
    WEEK = 5
    MONTH = 6


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProjectXAccount:
    id: int
    name: str
    balance: float
    can_trade: bool
    is_visible: bool


@dataclass(frozen=True)
class ProjectXPosition:
    id: int
    account_id: int
    contract_id: str
    creation_timestamp: str
    type: int  # 1 = long, 2 = short
    size: int
    average_price: float


@dataclass(frozen=True)
class ProjectXOrderResult:
    order_id: int | None
    success: bool
    error_code: int
    error_message: str | None


@dataclass(frozen=True)
class ProjectXBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# ── API Client ───────────────────────────────────────────────────────────────

class ProjectXClient:
    """Async HTTP client for the TopstepX / ProjectX API.

    Handles authentication, token refresh, and all API calls.
    Thread-safe for single-threaded async usage.
    """

    TOKEN_REFRESH_MARGIN = 300  # refresh token 5 minutes before expiry

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("TOPSTEPX_BASE_URL", "https://api.topstepx.com")).rstrip("/")
        self._email = email or os.getenv("TOPSTEPX_EMAIL", "")
        self._api_key = api_key or os.getenv("TOPSTEPX_API_KEY", "")
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ── Auth ──────────────────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Obtain a JWT session token via /api/Auth/loginKey.

        The userName field MUST be the account email, not the platform username.
        This is a known TopstepX quirk documented in our memory.
        """
        payload = {
            "userName": self._email,
            "apiKey": self._api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/api/Auth/loginKey",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            error_code = data.get("errorCode", "unknown")
            error_msg = data.get("errorMessage", "no message")
            raise RuntimeError(
                f"ProjectX auth failed: code={error_code}, msg={error_msg}"
            )

        self._token = data["token"]
        # Tokens typically expire in 24h; refresh 5 min early
        self._token_expiry = time.time() + (24 * 3600 - self.TOKEN_REFRESH_MARGIN)
        logger.info("ProjectX authenticated successfully")
        return self._token

    async def _ensure_token(self) -> str:
        """Get a valid token, authenticating or refreshing as needed."""
        if not self._token or time.time() >= self._token_expiry:
            await self.authenticate()
        assert self._token is not None
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "text/plain",
        }

    # ── Account ───────────────────────────────────────────────────────────

    async def search_accounts(self, only_active: bool = True) -> list[ProjectXAccount]:
        """POST /api/Account/search — list all accessible accounts."""
        headers = await self._headers()
        payload = {"onlyActiveAccounts": only_active}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/api/Account/search",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise RuntimeError(f"Account search failed: {data.get('errorMessage')}")

        return [
            ProjectXAccount(
                id=a["id"],
                name=a.get("name", ""),
                balance=float(a.get("balance", 0)),
                can_trade=a.get("canTrade", False),
                is_visible=a.get("isVisible", True),
            )
            for a in data.get("accounts", [])
        ]

    async def get_account(self, account_id: int) -> ProjectXAccount | None:
        """Find a specific account by ID."""
        accounts = await self.search_accounts()
        for acct in accounts:
            if acct.id == account_id:
                return acct
        return None

    # ── Positions ─────────────────────────────────────────────────────────

    async def search_open_positions(self, account_id: int) -> list[ProjectXPosition]:
        """POST /api/Position/searchOpen — list open positions for an account."""
        headers = await self._headers()
        payload = {"accountId": account_id}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/api/Position/searchOpen",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise RuntimeError(f"Position search failed: {data.get('errorMessage')}")

        return [
            ProjectXPosition(
                id=p["id"],
                account_id=p["accountId"],
                contract_id=p["contractId"],
                creation_timestamp=p.get("creationTimestamp", ""),
                type=p.get("type", 0),
                size=p.get("size", 0),
                average_price=float(p.get("averagePrice", 0)),
            )
            for p in data.get("positions", [])
        ]

    # ── Orders ────────────────────────────────────────────────────────────

    async def place_order(
        self,
        account_id: int,
        contract_id: str,
        side: OrderSide,
        size: int = 1,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        custom_tag: str | None = None,
        stop_loss_ticks: int | None = None,
        take_profit_ticks: int | None = None,
    ) -> ProjectXOrderResult:
        """POST /api/Order/place — place an order with optional brackets.

        ⚠️  This is the ONLY method that places real orders.
        It should ONLY be called through the full safety pipeline:
          TradeIntent → risk_daemon → execution_mode gates → audit_log → here

        Bracket orders:
          stopLossBracket.ticks  = stop distance in ticks
          takeProfitBracket.ticks = target distance in ticks
          type = 1 (Limit) for both brackets
        """
        headers = await self._headers()
        payload: dict = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": int(order_type),
            "side": int(side),
            "size": size,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "trailPrice": None,
            "customTag": custom_tag,
        }

        if stop_loss_ticks is not None and stop_loss_ticks > 0:
            payload["stopLossBracket"] = {"ticks": stop_loss_ticks, "type": 1}

        if take_profit_ticks is not None and take_profit_ticks > 0:
            payload["takeProfitBracket"] = {"ticks": take_profit_ticks, "type": 1}

        logger.info(
            "Placing %s order: account=%s contract=%s side=%s size=%s sl=%s tp=%s tag=%s",
            order_type.name, account_id, contract_id, side.name, size,
            stop_loss_ticks, take_profit_ticks, custom_tag,
        )

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/api/Order/place",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return ProjectXOrderResult(
            order_id=data.get("orderId"),
            success=data.get("success", False),
            error_code=data.get("errorCode", -1),
            error_message=data.get("errorMessage"),
        )

    # ── Market Data (History) ─────────────────────────────────────────────

    async def retrieve_bars(
        self,
        contract_id: str,
        start_time: str,
        end_time: str,
        unit: TimeframeUnit = TimeframeUnit.MINUTE,
        unit_number: int = 15,
        limit: int = 5000,
        live: bool = False,
    ) -> list[ProjectXBar]:
        """POST /api/History/retrieveBars — fetch OHLCV bars.

        Args:
            contract_id: e.g. "CON.F.US.MYM.M26"
            start_time: ISO datetime, e.g. "2026-01-01T00:00:00Z"
            end_time: ISO datetime, e.g. "2026-04-23T00:00:00Z"
            unit: aggregation unit (MINUTE, HOUR, DAY, etc.)
            unit_number: number of units per bar (e.g. 15 for 15-min bars)
            limit: max bars (up to 20,000)
            live: use live data subscription (vs sim)
        """
        headers = await self._headers()
        payload = {
            "contractId": contract_id,
            "live": live,
            "startTime": start_time,
            "endTime": end_time,
            "unit": int(unit),
            "unitNumber": unit_number,
            "limit": limit,
            "includePartialBar": False,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/api/History/retrieveBars",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise RuntimeError(f"History retrieve failed: {data.get('errorMessage')}")

        bars = []
        for b in data.get("bars", []):
            bars.append(ProjectXBar(
                timestamp=b.get("t", ""),
                open=float(b.get("o", 0)),
                high=float(b.get("h", 0)),
                low=float(b.get("l", 0)),
                close=float(b.get("c", 0)),
                volume=float(b.get("v", 0)),
            ))

        return bars
