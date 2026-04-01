"""
data/storage.py
===============
SQLite-backed persistence layer for the trading system.

Uses the stdlib ``sqlite3`` module only — no ORM dependency.
All public methods are synchronous; wrap in ``asyncio.to_thread``
if you need to call them from async contexts without blocking.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

from models import (
    Candle,
    Direction,
    MarketRegime,
    Order,
    OrderStatus,
    OrderType,
    Signal,
    Trade,
)

# ISO-8601 format used for all datetime serialisation
_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(_DT_FMT) if dt is not None else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(s, _DT_FMT) if s else None


class Storage:
    """
    Thin SQLite wrapper that persists all trading artefacts.

    All tables are created automatically on first access.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Parent directories are
        created automatically.
    """

    def __init__(self, db_path: str = "data/trading.db") -> None:
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
        CREATE TABLE IF NOT EXISTS candles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument  TEXT    NOT NULL,
            timeframe   TEXT    NOT NULL,
            time        TEXT    NOT NULL,
            open        REAL    NOT NULL,
            high        REAL    NOT NULL,
            low         REAL    NOT NULL,
            close       REAL    NOT NULL,
            volume      REAL    NOT NULL,
            UNIQUE(instrument, timeframe, time)
        );

        CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles(instrument, timeframe, time);

        CREATE TABLE IF NOT EXISTS signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument      TEXT    NOT NULL,
            direction       TEXT    NOT NULL,
            strategy_name   TEXT    NOT NULL,
            entry_price     REAL    NOT NULL,
            stop_loss       REAL    NOT NULL,
            take_profit     REAL,
            size_hint       REAL    NOT NULL DEFAULT 1.0,
            confidence      REAL    NOT NULL DEFAULT 1.0,
            regime          TEXT    NOT NULL,
            timestamp       TEXT    NOT NULL,
            metadata        TEXT    NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS orders (
            id                  TEXT    PRIMARY KEY,
            instrument          TEXT    NOT NULL,
            direction           TEXT    NOT NULL,
            order_type          TEXT    NOT NULL,
            quantity            REAL    NOT NULL,
            price               REAL,
            stop_price          REAL,
            status              TEXT    NOT NULL,
            strategy_name       TEXT    NOT NULL,
            broker_order_id     TEXT,
            filled_price        REAL,
            filled_quantity     REAL    NOT NULL DEFAULT 0.0,
            created_at          TEXT    NOT NULL,
            filled_at           TEXT,
            metadata            TEXT    NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_orders_status
            ON orders(status);

        CREATE TABLE IF NOT EXISTS trades (
            id              TEXT    PRIMARY KEY,
            instrument      TEXT    NOT NULL,
            direction       TEXT    NOT NULL,
            quantity        REAL    NOT NULL,
            entry_price     REAL    NOT NULL,
            exit_price      REAL    NOT NULL,
            pnl             REAL    NOT NULL,
            pnl_pct         REAL    NOT NULL,
            strategy_name   TEXT    NOT NULL,
            regime          TEXT    NOT NULL,
            opened_at       TEXT    NOT NULL,
            closed_at       TEXT    NOT NULL,
            metadata        TEXT    NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_trades_closed
            ON trades(closed_at);

        CREATE TABLE IF NOT EXISTS equity_curve (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            equity          REAL    NOT NULL,
            cash            REAL    NOT NULL,
            unrealized_pnl  REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS regime_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument  TEXT    NOT NULL,
            timeframe   TEXT    NOT NULL,
            regime      TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_regime_log_instrument
            ON regime_log(instrument, timeframe, timestamp);
        """
        self._conn.executescript(ddl)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    def save_candle(self, candle: Candle) -> None:
        """Upsert a single candle bar (ignores duplicates)."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO candles
                (instrument, timeframe, time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candle.instrument,
                candle.timeframe,
                _dt_to_str(candle.time),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            ),
        )
        self._conn.commit()

    def save_candles(self, candles: list[Candle]) -> None:
        """Batch upsert multiple candle bars efficiently."""
        self._conn.executemany(
            """
            INSERT OR IGNORE INTO candles
                (instrument, timeframe, time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c.instrument,
                    c.timeframe,
                    _dt_to_str(c.time),
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                )
                for c in candles
            ],
        )
        self._conn.commit()

    def get_candles(
        self,
        instrument: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[Candle]:
        """
        Retrieve stored candle bars for a given instrument and timeframe.

        Parameters
        ----------
        instrument:
            Instrument symbol.
        timeframe:
            Granularity string, e.g. ``"5m"``.
        start:
            Inclusive lower bound on bar time.  ``None`` means no lower bound.
        end:
            Inclusive upper bound on bar time.  ``None`` means no upper bound.

        Returns
        -------
        list[Candle]
            Bars in chronological order.
        """
        query = (
            "SELECT * FROM candles "
            "WHERE instrument = ? AND timeframe = ?"
        )
        params: list = [instrument, timeframe]

        if start is not None:
            query += " AND time >= ?"
            params.append(_dt_to_str(start))
        if end is not None:
            query += " AND time <= ?"
            params.append(_dt_to_str(end))

        query += " ORDER BY time ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [
            Candle(
                time=_str_to_dt(row["time"]),  # type: ignore[arg-type]
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                instrument=row["instrument"],
                timeframe=row["timeframe"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def save_signal(self, signal: Signal) -> None:
        """Persist a strategy signal."""
        self._conn.execute(
            """
            INSERT INTO signals
                (instrument, direction, strategy_name, entry_price, stop_loss,
                 take_profit, size_hint, confidence, regime, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.instrument,
                signal.direction.value,
                signal.strategy_name,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit,
                signal.size_hint,
                signal.confidence,
                signal.regime.value,
                _dt_to_str(signal.timestamp),
                json.dumps(signal.metadata),
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def save_order(self, order: Order) -> None:
        """Insert a new order record."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO orders
                (id, instrument, direction, order_type, quantity, price,
                 stop_price, status, strategy_name, broker_order_id,
                 filled_price, filled_quantity, created_at, filled_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.id,
                order.instrument,
                order.direction.value,
                order.order_type.value,
                order.quantity,
                order.price,
                order.stop_price,
                order.status.value,
                order.strategy_name,
                order.broker_order_id,
                order.filled_price,
                order.filled_quantity,
                _dt_to_str(order.created_at),
                _dt_to_str(order.filled_at),
                json.dumps(order.metadata),
            ),
        )
        self._conn.commit()

    def update_order(self, order: Order) -> None:
        """Update a mutable order record (status, fill info, etc.)."""
        self._conn.execute(
            """
            UPDATE orders SET
                status          = ?,
                broker_order_id = ?,
                filled_price    = ?,
                filled_quantity = ?,
                filled_at       = ?,
                metadata        = ?
            WHERE id = ?
            """,
            (
                order.status.value,
                order.broker_order_id,
                order.filled_price,
                order.filled_quantity,
                _dt_to_str(order.filled_at),
                json.dumps(order.metadata),
                order.id,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def save_trade(self, trade: Trade) -> None:
        """Persist a completed trade."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO trades
                (id, instrument, direction, quantity, entry_price, exit_price,
                 pnl, pnl_pct, strategy_name, regime, opened_at, closed_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.id,
                trade.instrument,
                trade.direction.value,
                trade.quantity,
                trade.entry_price,
                trade.exit_price,
                trade.pnl,
                trade.pnl_pct,
                trade.strategy_name,
                trade.regime,
                _dt_to_str(trade.opened_at),
                _dt_to_str(trade.closed_at),
                json.dumps(trade.metadata),
            ),
        )
        self._conn.commit()

    def get_trades(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        strategy: Optional[str] = None,
    ) -> list[Trade]:
        """
        Retrieve completed trades with optional filters.

        Parameters
        ----------
        start:
            Inclusive lower bound on ``closed_at``.
        end:
            Inclusive upper bound on ``closed_at``.
        strategy:
            Filter to a single strategy by name.

        Returns
        -------
        list[Trade]
            Trades ordered by ``closed_at`` ascending.
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []

        if start is not None:
            query += " AND closed_at >= ?"
            params.append(_dt_to_str(start))
        if end is not None:
            query += " AND closed_at <= ?"
            params.append(_dt_to_str(end))
        if strategy is not None:
            query += " AND strategy_name = ?"
            params.append(strategy)

        query += " ORDER BY closed_at ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [
            Trade(
                id=row["id"],
                instrument=row["instrument"],
                direction=Direction(row["direction"]),
                quantity=row["quantity"],
                entry_price=row["entry_price"],
                exit_price=row["exit_price"],
                pnl=row["pnl"],
                pnl_pct=row["pnl_pct"],
                strategy_name=row["strategy_name"],
                regime=row["regime"],
                opened_at=_str_to_dt(row["opened_at"]),  # type: ignore[arg-type]
                closed_at=_str_to_dt(row["closed_at"]),  # type: ignore[arg-type]
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Equity curve
    # ------------------------------------------------------------------

    def record_equity(
        self,
        timestamp: datetime,
        equity: float,
        cash: float,
        unrealized_pnl: float,
    ) -> None:
        """Append a snapshot to the equity curve table."""
        self._conn.execute(
            """
            INSERT INTO equity_curve (timestamp, equity, cash, unrealized_pnl)
            VALUES (?, ?, ?, ?)
            """,
            (_dt_to_str(timestamp), equity, cash, unrealized_pnl),
        )
        self._conn.commit()

    def get_equity_curve(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Retrieve equity snapshots as a list of plain dicts.

        Each dict has keys: ``timestamp`` (datetime), ``equity``,
        ``cash``, ``unrealized_pnl``.
        """
        query = "SELECT * FROM equity_curve WHERE 1=1"
        params: list = []

        if start is not None:
            query += " AND timestamp >= ?"
            params.append(_dt_to_str(start))
        if end is not None:
            query += " AND timestamp <= ?"
            params.append(_dt_to_str(end))

        query += " ORDER BY timestamp ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "timestamp": _str_to_dt(row["timestamp"]),
                "equity": row["equity"],
                "cash": row["cash"],
                "unrealized_pnl": row["unrealized_pnl"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Regime log
    # ------------------------------------------------------------------

    def log_regime(
        self,
        instrument: str,
        timeframe: str,
        regime: str,
        timestamp: datetime,
    ) -> None:
        """Append a market-regime observation to the regime log."""
        self._conn.execute(
            """
            INSERT INTO regime_log (instrument, timeframe, regime, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (instrument, timeframe, regime, _dt_to_str(timestamp)),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Flush WAL and close the database connection."""
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *_) -> None:
        self.close()
