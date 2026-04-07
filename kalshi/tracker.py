"""
kalshi/tracker.py
=================
Real-time Kalshi orderbook tracker.

Connects to Kalshi's WebSocket API, maintains an in-memory orderbook
state by applying incremental deltas, and persists every change to
SQLite for later analysis.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from kalshi.client import KalshiClient
from kalshi.storage import KalshiStorage

_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime(_DT_FMT)


def _sorted_bids(book: dict[int, int]) -> list[list]:
    """Return [[price, qty], ...] sorted highest price first."""
    return [[p, q] for p, q in sorted(book.items(), reverse=True) if q > 0]


class OrderbookTracker:
    """
    Tracks a Kalshi market orderbook for a configurable time window.

    Parameters
    ----------
    ticker:
        Explicit market ticker (e.g. "KXBTC15M-26APR071030"), or None to
        auto-detect the currently live market from `series_ticker`.
    series_ticker:
        Series to auto-discover the live market from (default "KXBTC15M").
        Only used when `ticker` is None.
    window_minutes:
        How long to track per market (0 = run until Ctrl-C, following each
        market as it opens).
    continuous:
        If True, after one market closes automatically wait for and switch
        to the next one. Requires window_minutes=0 or matching the market
        duration. Ignored when window_minutes > 0 and a specific ticker is
        given.
    db_path:
        Path to the SQLite database for storing snapshots.
    verbose:
        Print a summary line on every update if True.
    """

    def __init__(
        self,
        ticker: Optional[str] = None,
        series_ticker: str = "KXBTC15M",
        window_minutes: int = 15,
        continuous: bool = False,
        db_path: str = "data/kalshi.db",
        verbose: bool = True,
    ) -> None:
        self.ticker = ticker
        self.series_ticker = series_ticker
        self.window_minutes = window_minutes
        self.continuous = continuous
        self.db_path = db_path
        self.verbose = verbose

        self._yes: dict[int, int] = {}
        self._no: dict[int, int] = {}
        self._seq = 0
        self._count = 0
        self._session_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect, track, and store. Blocks until done."""
        storage = KalshiStorage(self.db_path)

        try:
            async with KalshiClient() as client:
                if self.continuous or self.ticker is None:
                    await self._run_continuous(client, storage)
                else:
                    await self._run_single(client, storage, self.ticker)
        except KeyboardInterrupt:
            print(f"\n[tracker] interrupted — {self._count} total rows in {self.db_path}")
        finally:
            storage.close()

    # ------------------------------------------------------------------
    # Internal: single-window run
    # ------------------------------------------------------------------

    async def _run_single(
        self, client: KalshiClient, storage: KalshiStorage, ticker: str
    ) -> None:
        """Track one market ticker for window_minutes, then stop."""
        session_id = str(uuid.uuid4())
        storage.create_session(session_id, ticker, self.window_minutes)
        count = 0

        deadline = (
            asyncio.get_event_loop().time() + self.window_minutes * 60
            if self.window_minutes > 0
            else None
        )

        print(f"[tracker] ticker={ticker}  session={session_id[:8]}...")
        if deadline:
            print(f"[tracker] tracking for {self.window_minutes} minutes → {self.db_path}")
        else:
            print(f"[tracker] tracking until Ctrl-C → {self.db_path}")

        # Reset book state for this market
        self._yes = {}
        self._no = {}
        self._seq = 0

        await client.subscribe_orderbook(ticker)
        print("[tracker] subscribed, waiting for data...")

        async for msg in client.iter_messages():
            if deadline and asyncio.get_event_loop().time() >= deadline:
                print(f"\n[tracker] window complete — {count} snapshots for {ticker}")
                break

            delta = self._handle_message(msg, storage, session_id, ticker)
            count += delta
            self._count += delta

        storage.close_session(session_id, count)

    # ------------------------------------------------------------------
    # Internal: continuous multi-window run
    # ------------------------------------------------------------------

    async def _run_continuous(
        self, client: KalshiClient, storage: KalshiStorage
    ) -> None:
        """
        Continuously track markets in the series: detect the live ticker,
        track it until it closes, then wait for the next one.
        """
        print(f"[tracker] continuous mode — series={self.series_ticker}")
        windows = 0
        while True:
            # Resolve current live ticker
            ticker = self.ticker
            if ticker is None:
                print(f"[tracker] looking up live {self.series_ticker} market...")
                ticker = await client.wait_for_live_ticker(self.series_ticker)
                print(f"[tracker] found live ticker: {ticker}")

            await self._run_single(client, storage, ticker)
            windows += 1
            print(f"[tracker] completed window #{windows} ({ticker})")

            if not self.continuous:
                break

            # Between windows: wait for the next market to open
            print(f"[tracker] waiting for next {self.series_ticker} market...")
            # Brief pause so the just-closed market stops appearing as "open"
            await asyncio.sleep(5)
            ticker = await client.wait_for_live_ticker(
                self.series_ticker, poll_interval=10, timeout=600
            )
            # Reset ticker so it auto-discovers each cycle
            self.ticker = None

    # ------------------------------------------------------------------
    # Internal message handling
    # ------------------------------------------------------------------

    def _handle_message(
        self,
        msg: dict,
        storage: KalshiStorage,
        session_id: str,
        ticker: str,
    ) -> int:
        """Process one WS message. Returns 1 if a snapshot was saved, else 0."""
        msg_type = msg.get("type", "")

        if msg_type == "subscribed":
            print(f"[tracker] confirmed subscribed to channel={msg.get('msg', {}).get('channel')}")
            return 0

        if msg_type not in ("orderbook_snapshot", "orderbook_delta"):
            return 0

        inner = msg.get("msg", {})
        if inner.get("market_ticker") != ticker:
            return 0

        self._seq = msg.get("seq", self._seq + 1)
        ts = _utcnow()

        if msg_type == "orderbook_snapshot":
            self._yes = {p: q for p, q in inner.get("yes", []) if q > 0}
            self._no = {p: q for p, q in inner.get("no", []) if q > 0}
            event = "snapshot"
        else:
            for price, delta in inner.get("yes", []):
                new_qty = self._yes.get(price, 0) + delta
                if new_qty <= 0:
                    self._yes.pop(price, None)
                else:
                    self._yes[price] = new_qty

            for price, delta in inner.get("no", []):
                new_qty = self._no.get(price, 0) + delta
                if new_qty <= 0:
                    self._no.pop(price, None)
                else:
                    self._no[price] = new_qty

            event = "delta"

        yes_bids = _sorted_bids(self._yes)
        no_bids = _sorted_bids(self._no)

        storage.save_snapshot(
            ticker=ticker,
            session_id=session_id,
            timestamp=ts,
            yes_bids=yes_bids,
            no_bids=no_bids,
            seq=self._seq,
            event=event,
        )

        if self.verbose:
            best_yes = yes_bids[0][0] if yes_bids else "?"
            best_no = no_bids[0][0] if no_bids else "?"
            total = self._count + 1
            if isinstance(best_yes, (int, float)) and isinstance(best_no, (int, float)):
                spread = 100 - best_yes - best_no
                print(
                    f"  [{total:>5}] {ts[11:23]}  "
                    f"YES={best_yes:>3}¢  NO={best_no:>3}¢  "
                    f"spread={spread:>+.0f}¢  [{event}]  {ticker}"
                )
            else:
                print(f"  [{total:>5}] {ts[11:23]}  YES={best_yes}  NO={best_no}  [{event}]  {ticker}")

        return 1

    # ------------------------------------------------------------------
    # Internal message handling
    # ------------------------------------------------------------------

    def _handle_message(self, msg: dict, storage: KalshiStorage) -> None:
        msg_type = msg.get("type", "")

        if msg_type == "subscribed":
            print(f"[tracker] confirmed subscribed to channel={msg.get('msg', {}).get('channel')}")
            return

        if msg_type not in ("orderbook_snapshot", "orderbook_delta"):
            return

        inner = msg.get("msg", {})
        if inner.get("market_ticker") != self.ticker:
            return

        self._seq = msg.get("seq", self._seq + 1)
        ts = _utcnow()

        if msg_type == "orderbook_snapshot":
            # Full replacement
            self._yes = {p: q for p, q in inner.get("yes", []) if q > 0}
            self._no = {p: q for p, q in inner.get("no", []) if q > 0}
            event = "snapshot"
        else:
            # Incremental delta: apply changes
            for price, delta in inner.get("yes", []):
                new_qty = self._yes.get(price, 0) + delta
                if new_qty <= 0:
                    self._yes.pop(price, None)
                else:
                    self._yes[price] = new_qty

            for price, delta in inner.get("no", []):
                new_qty = self._no.get(price, 0) + delta
                if new_qty <= 0:
                    self._no.pop(price, None)
                else:
                    self._no[price] = new_qty

            event = "delta"

        yes_bids = _sorted_bids(self._yes)
        no_bids = _sorted_bids(self._no)

        storage.save_snapshot(
            ticker=self.ticker,
            session_id=self._session_id,
            timestamp=ts,
            yes_bids=yes_bids,
            no_bids=no_bids,
            seq=self._seq,
            event=event,
        )
        self._count += 1

        if self.verbose:
            best_yes = yes_bids[0][0] if yes_bids else "?"
            best_no = no_bids[0][0] if no_bids else "?"
            if isinstance(best_yes, (int, float)) and isinstance(best_no, (int, float)):
                spread = 100 - best_yes - best_no
                print(
                    f"  [{self._count:>5}] {ts[11:23]}  "
                    f"YES={best_yes:>3}¢  NO={best_no:>3}¢  "
                    f"spread={spread:>+.0f}¢  [{event}]"
                )
            else:
                print(f"  [{self._count:>5}] {ts[11:23]}  YES={best_yes}  NO={best_no}  [{event}]")
