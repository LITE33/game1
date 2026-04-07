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
        Kalshi market ticker, e.g. "KXBTC15M-26APR071030".
    window_minutes:
        How long to track (0 = run until Ctrl-C).
    db_path:
        Path to the SQLite database for storing snapshots.
    verbose:
        Print a summary line on every update if True.
    """

    def __init__(
        self,
        ticker: str,
        window_minutes: int = 15,
        db_path: str = "data/kalshi.db",
        verbose: bool = True,
    ) -> None:
        self.ticker = ticker
        self.window_minutes = window_minutes
        self.db_path = db_path
        self.verbose = verbose

        # In-memory orderbook state: price_cents -> quantity
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
        storage.create_session(self._session_id, self.ticker, self.window_minutes)

        deadline = (
            asyncio.get_event_loop().time() + self.window_minutes * 60
            if self.window_minutes > 0
            else None
        )

        print(f"[tracker] session={self._session_id[:8]}... ticker={self.ticker}")
        if self.window_minutes > 0:
            print(f"[tracker] tracking for {self.window_minutes} minutes → {self.db_path}")
        else:
            print(f"[tracker] tracking indefinitely (Ctrl-C to stop) → {self.db_path}")

        try:
            async with KalshiClient() as client:
                await client.subscribe_orderbook(self.ticker)
                print("[tracker] subscribed, waiting for data...")

                async for msg in client.iter_messages():
                    if deadline and asyncio.get_event_loop().time() >= deadline:
                        print(f"\n[tracker] window complete after {self._count} snapshots")
                        break

                    self._handle_message(msg, storage)

        except KeyboardInterrupt:
            print(f"\n[tracker] interrupted after {self._count} snapshots")
        except Exception as exc:
            print(f"\n[tracker] error: {exc}", file=sys.stderr)
            raise
        finally:
            storage.close_session(self._session_id, self._count)
            storage.close()
            print(f"[tracker] session closed — {self._count} rows in {self.db_path}")

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
