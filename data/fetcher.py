"""
data/fetcher.py
===============
DataFetcher orchestrates historical candle retrieval across brokers
with a transparent SQLite cache layer.

Flow
----
1. Check the SQLite cache (``Storage``) for the requested bars.
2. If the cache has enough bars, return them directly.
3. Otherwise fetch from the appropriate broker, store in cache, return.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from brokers.base import BrokerBase
from data.storage import Storage
from models import Candle


class DataFetcher:
    """
    Unified candle data retrieval with broker failover and local caching.

    Parameters
    ----------
    brokers:
        List of broker adapters available to fetch from.
    storage:
        SQLite storage instance used as the persistent cache.
    """

    def __init__(self, brokers: list[BrokerBase], storage: Storage) -> None:
        self._brokers: dict[str, BrokerBase] = {b.name: b for b in brokers}
        self._storage = storage

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_broker(
        self,
        instrument: str,
        broker_name: Optional[str],
    ) -> BrokerBase:
        """
        Return the broker to use for *instrument*.

        If *broker_name* is provided, that broker is used directly.
        Otherwise the first broker whose ``supported_instruments`` list
        includes *instrument* is selected.

        Raises
        ------
        ValueError
            If no suitable broker is found.
        """
        if broker_name is not None:
            if broker_name not in self._brokers:
                raise ValueError(
                    f"Broker {broker_name!r} is not registered. "
                    f"Available: {list(self._brokers)}"
                )
            return self._brokers[broker_name]

        for broker in self._brokers.values():
            if instrument in broker.supported_instruments:
                return broker

        raise ValueError(
            f"No registered broker supports instrument {instrument!r}. "
            f"Available brokers: {list(self._brokers)}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_historical(
        self,
        instrument: str,
        timeframe: str,
        count: int,
        broker_name: Optional[str] = None,
    ) -> list[Candle]:
        """
        Fetch up to *count* historical candles for *instrument*/*timeframe*.

        The SQLite cache is checked first.  If it contains at least *count*
        completed bars they are returned without any broker call.  Otherwise
        the broker is queried, the result is merged into the cache, and the
        most recent *count* bars are returned.

        Parameters
        ----------
        instrument:
            Symbol string, e.g. ``"EUR_USD"`` or ``"MES"``.
        timeframe:
            Granularity, e.g. ``"5m"``, ``"1h"``.
        count:
            Desired number of bars (most recent *count* bars).
        broker_name:
            Optional override to choose a specific broker adapter.

        Returns
        -------
        list[Candle]
            Bars in chronological order (oldest first), length <= *count*.
        """
        # Try cache first
        cached = self._storage.get_candles(instrument, timeframe)
        if len(cached) >= count:
            return cached[-count:]

        # Fetch from broker and cache the result
        broker = self._select_broker(instrument, broker_name)
        fresh = await broker.get_candles(instrument, timeframe, count)

        if fresh:
            self._storage.save_candles(fresh)

        # Re-query the cache so deduplication is respected
        merged = self._storage.get_candles(instrument, timeframe)
        return merged[-count:] if len(merged) >= count else merged

    async def fetch_candles_df(
        self,
        instrument: str,
        timeframe: str,
        count: int,
        broker_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical candles and return them as a ``pd.DataFrame``.

        Equivalent to calling :meth:`fetch_historical` then
        :meth:`candles_to_df`.

        Parameters
        ----------
        instrument:
            Symbol string.
        timeframe:
            Granularity string.
        count:
            Number of bars to retrieve.
        broker_name:
            Optional broker override.

        Returns
        -------
        pd.DataFrame
            Columns: ``open``, ``high``, ``low``, ``close``, ``volume``.
            Index: ``time`` (``datetime``), ascending.
        """
        candles = await self.fetch_historical(instrument, timeframe, count, broker_name)
        return self.candles_to_df(candles)

    @staticmethod
    def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
        """
        Convert a list of :class:`~models.Candle` objects to a DataFrame.

        Parameters
        ----------
        candles:
            Bars in any order (they will be sorted by time ascending).

        Returns
        -------
        pd.DataFrame
            Columns: ``open``, ``high``, ``low``, ``close``, ``volume``.
            Index name: ``time``, dtype ``datetime64[ns]``, ascending.
            Returns an empty DataFrame with the correct schema if
            *candles* is empty.
        """
        if not candles:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"],
                index=pd.DatetimeIndex([], name="time"),
            )

        records = [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

        df = pd.DataFrame(records)
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time").set_index("time")
        return df

    # ------------------------------------------------------------------
    # Broker management
    # ------------------------------------------------------------------

    def register_broker(self, broker: BrokerBase) -> None:
        """Register an additional broker adapter at runtime."""
        self._brokers[broker.name] = broker

    def get_broker(self, name: str) -> BrokerBase:
        """Return a registered broker by name."""
        if name not in self._brokers:
            raise KeyError(f"Broker {name!r} not registered.")
        return self._brokers[name]

    @property
    def broker_names(self) -> list[str]:
        """Names of all currently registered brokers."""
        return list(self._brokers)
