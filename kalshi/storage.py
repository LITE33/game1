"""
kalshi/storage.py
=================
SQLite persistence for Kalshi orderbook data.

Follows the same pattern as data/storage.py (stdlib sqlite3, WAL mode,
synchronous methods). Uses a dedicated database file so Kalshi data
stays separate from the main trading database.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

try:
    import pandas as pd
    _PANDAS = True
except ImportError:
    _PANDAS = False

_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _now_str() -> str:
    return datetime.utcnow().strftime(_DT_FMT)


class KalshiStorage:
    """
    Persists Kalshi orderbook snapshots and session metadata.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file (created automatically).
    """

    def __init__(self, db_path: str = "data/kalshi.db") -> None:
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            session_id  TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL,
            seq         INTEGER NOT NULL DEFAULT 0,
            yes_bids    TEXT    NOT NULL,
            no_bids     TEXT    NOT NULL,
            best_yes    REAL,
            best_no     REAL,
            spread      REAL,
            yes_depth   REAL,
            no_depth    REAL,
            event       TEXT    NOT NULL DEFAULT 'delta'
        );

        CREATE INDEX IF NOT EXISTS idx_ob_ticker_time
            ON orderbook_snapshots(ticker, timestamp);

        CREATE INDEX IF NOT EXISTS idx_ob_session
            ON orderbook_snapshots(session_id);

        CREATE TABLE IF NOT EXISTS orderbook_sessions (
            session_id      TEXT    PRIMARY KEY,
            ticker          TEXT    NOT NULL,
            start_time      TEXT    NOT NULL,
            end_time        TEXT,
            window_min      INTEGER NOT NULL DEFAULT 15,
            snapshot_count  INTEGER NOT NULL DEFAULT 0
        );
        """
        self._conn.executescript(ddl)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, ticker: str, window_min: int = 15) -> None:
        """Record the start of a tracking session."""
        self._conn.execute(
            """
            INSERT INTO orderbook_sessions (session_id, ticker, start_time, window_min)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, ticker, _now_str(), window_min),
        )
        self._conn.commit()

    def close_session(self, session_id: str, snapshot_count: int) -> None:
        """Mark a session as complete with final snapshot count."""
        self._conn.execute(
            """
            UPDATE orderbook_sessions
               SET end_time = ?, snapshot_count = ?
             WHERE session_id = ?
            """,
            (_now_str(), snapshot_count, session_id),
        )
        self._conn.commit()

    def get_sessions(self, ticker: Optional[str] = None) -> list[dict]:
        """Return all sessions, optionally filtered by ticker."""
        if ticker:
            rows = self._conn.execute(
                "SELECT * FROM orderbook_sessions WHERE ticker = ? ORDER BY start_time DESC",
                (ticker,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM orderbook_sessions ORDER BY start_time DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        ticker: str,
        session_id: str,
        timestamp: str,
        yes_bids: list,
        no_bids: list,
        seq: int = 0,
        event: str = "delta",
    ) -> None:
        """
        Persist one orderbook state.

        yes_bids / no_bids are lists of [price_cents, quantity] sorted
        best (highest) first.
        """
        best_yes = yes_bids[0][0] if yes_bids else None
        best_no = no_bids[0][0] if no_bids else None
        spread = (100 - best_yes - best_no) if (best_yes is not None and best_no is not None) else None
        yes_depth = sum(q for _, q in yes_bids)
        no_depth = sum(q for _, q in no_bids)

        self._conn.execute(
            """
            INSERT INTO orderbook_snapshots
                (ticker, session_id, timestamp, seq, yes_bids, no_bids,
                 best_yes, best_no, spread, yes_depth, no_depth, event)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                session_id,
                timestamp,
                seq,
                json.dumps(yes_bids),
                json.dumps(no_bids),
                best_yes,
                best_no,
                spread,
                yes_depth,
                no_depth,
                event,
            ),
        )
        self._conn.commit()

    def get_snapshots(
        self,
        ticker: str,
        session_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Return raw snapshot rows as dicts.

        `ticker` can be an exact market ticker ("KXBTC15M-26APR071030") or
        a series prefix ("KXBTC15M") to match all markets in that series.
        """
        if "-" in ticker:
            # Exact match
            sql = "SELECT * FROM orderbook_snapshots WHERE ticker = ?"
            params: list = [ticker]
        else:
            # Prefix match (series)
            sql = "SELECT * FROM orderbook_snapshots WHERE ticker LIKE ?"
            params = [f"{ticker}-%"]

        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY timestamp ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_snapshots_df(
        self,
        ticker: str,
        session_id: Optional[str] = None,
    ):
        """
        Return snapshots as a pandas DataFrame (requires pandas).

        `ticker` accepts exact market tickers or a series prefix like "KXBTC15M"
        to load all data across all windows in that series.

        Columns: id, ticker, session_id, timestamp, seq, yes_bids, no_bids,
                 best_yes, best_no, spread, yes_depth, no_depth, event
        """
        if not _PANDAS:
            raise ImportError("pandas is required for get_snapshots_df()")
        rows = self.get_snapshots(ticker, session_id)
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["yes_bids"] = df["yes_bids"].apply(json.loads)
        df["no_bids"] = df["no_bids"].apply(json.loads)
        return df

    def close(self) -> None:
        self._conn.close()
