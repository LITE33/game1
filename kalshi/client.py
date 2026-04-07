"""
kalshi/client.py
================
Async Kalshi API client for orderbook data.

Uses aiohttp for REST and websockets for real-time streaming.
No authentication required for public orderbook data.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

import aiohttp

BASE_REST = "https://api.elections.kalshi.com/trade-api/v2"
BASE_WS = "wss://api.elections.kalshi.com/trade-api/ws/v2"


class KalshiClient:
    """
    Async client for Kalshi public market data.

    Usage (REST)::

        async with KalshiClient() as client:
            book = await client.get_orderbook("KXBTC15M-26APR071030")

    Usage (WebSocket)::

        async with KalshiClient() as client:
            await client.subscribe_orderbook("KXBTC15M-26APR071030")
            async for msg in client.iter_messages():
                print(msg)
    """

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._msg_id = 0

    async def __aenter__(self) -> "KalshiClient":
        self._session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"}
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        """
        Fetch current orderbook snapshot via REST.

        Returns dict with keys 'yes' and 'no', each a list of
        [price_cents, quantity] pairs sorted best-to-worst.
        """
        url = f"{BASE_REST}/markets/{ticker}/orderbook"
        params = {"depth": depth}
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("orderbook", {})

    async def get_market(self, ticker: str) -> dict:
        """Fetch market metadata (title, close_time, status, etc.)."""
        url = f"{BASE_REST}/markets/{ticker}"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("market", {})

    async def get_live_ticker(self, series_ticker: str = "KXBTC15M") -> Optional[str]:
        """
        Find the currently open market ticker for a given series.

        Queries the markets list filtered to open/active status and returns
        the ticker of the market closest to expiry (the one currently trading).

        Returns None if no open market is found right now (e.g. between windows).
        """
        url = f"{BASE_REST}/markets"
        params = {
            "series_ticker": series_ticker,
            "status": "open",
            "limit": 10,
        }
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        markets = data.get("markets", [])
        if not markets:
            return None

        # Pick the market expiring soonest — that's the live one
        def close_key(m: dict) -> str:
            return m.get("close_time") or m.get("expiration_time") or ""

        markets.sort(key=close_key)
        return markets[0]["ticker"]

    async def wait_for_live_ticker(
        self,
        series_ticker: str = "KXBTC15M",
        poll_interval: int = 10,
        timeout: int = 300,
    ) -> str:
        """
        Poll until an open market appears for the series (e.g. between windows).
        Raises TimeoutError if none appears within `timeout` seconds.
        """
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ticker = await self.get_live_ticker(series_ticker)
            if ticker:
                return ticker
            remaining = int(deadline - time.monotonic())
            print(f"[client] no open market for {series_ticker}, retrying in {poll_interval}s "
                  f"(timeout in {remaining}s)...")
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"No open {series_ticker} market found within {timeout}s")

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def connect_ws(self) -> None:
        """Open WebSocket connection to Kalshi streaming API."""
        self._ws = await self._session.ws_connect(
            BASE_WS,
            heartbeat=30,
            receive_timeout=60,
        )

    async def subscribe_orderbook(self, ticker: str) -> None:
        """
        Subscribe to orderbook_delta channel for the given ticker.
        The first message received will be a full snapshot; subsequent
        messages are incremental deltas.
        """
        if self._ws is None or self._ws.closed:
            await self.connect_ws()

        self._msg_id += 1
        payload = {
            "id": self._msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": [ticker],
            },
        }
        await self._ws.send_str(json.dumps(payload))

    async def iter_messages(self) -> AsyncIterator[dict]:
        """
        Yield parsed JSON messages from the WebSocket stream.
        Handles ping/pong automatically (aiohttp heartbeat).
        Raises StopAsyncIteration when the connection closes.
        """
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                yield json.loads(msg.data)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise ConnectionError(f"WebSocket error: {msg.data}")
