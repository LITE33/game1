"""
strategies/base.py
==================
Abstract base class for all trading strategies.

Every concrete strategy must subclass ``Strategy`` and implement
``on_candle``.  The engine calls ``on_candle`` on each newly completed
bar, passing both the latest :class:`~models.Candle` and the full
historical :class:`~pandas.DataFrame` (including that bar) so the
strategy can compute indicators without having to manage its own
lookback buffer.

Lifecycle
---------
1. ``__init__`` — configure instruments, timeframe, and settings.
2. Engine calls ``on_candle`` for every new completed bar.
3. Strategy returns a :class:`~models.Signal` or ``None``.
4. Engine passes any non-``None`` signal to the risk manager.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from config.settings import Settings
from models import Candle, Signal

logger = logging.getLogger(__name__)


class Strategy(ABC):
    """
    Abstract base for all trading strategies.

    Parameters
    ----------
    name:
        Human-readable strategy identifier.  Must be unique across all
        loaded strategies.
    instruments:
        List of instrument symbols this strategy watches, e.g.
        ``["EUR_USD", "GBP_USD"]``.
    timeframe:
        Primary candle resolution, e.g. ``"5m"``, ``"1h"``.
    settings:
        Application-wide settings (injected by the engine).
    """

    def __init__(
        self,
        name: str,
        instruments: list[str],
        timeframe: str,
        settings: Settings,
    ) -> None:
        self._name = name
        self._instruments = list(instruments)
        self._timeframe = timeframe
        self._settings = settings
        self._enabled = True

        logger.debug(
            "Strategy initialised: name=%r instruments=%r timeframe=%r",
            name,
            instruments,
            timeframe,
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def on_candle(self, candle: Candle, df: pd.DataFrame) -> Optional[Signal]:
        """
        Process a newly completed candle and optionally emit a signal.

        This is the primary hook called by the trading engine.  It must
        be fast and *non-blocking* — heavy computation should be
        pre-computed where possible.

        Parameters
        ----------
        candle:
            The bar that just closed.  Its fields mirror the last row
            of *df*.
        df:
            Full historical OHLCV DataFrame up to and including *candle*,
            indexed by ``time`` (ascending).  The strategy is free to run
            any indicator computation on this DataFrame.

            Columns: ``open``, ``high``, ``low``, ``close``, ``volume``.

        Returns
        -------
        Signal or None
            Return a :class:`~models.Signal` to enter a trade, or
            ``None`` to pass (no action).

        Notes
        -----
        - ``df`` will have at least :attr:`required_history` rows when
          the engine considers the strategy "warmed up"; before that
          ``on_candle`` is still called but the strategy should return
          ``None`` until it has enough history.
        - The strategy must **not** modify *df* in place.
        """

    # ------------------------------------------------------------------
    # Enabled / disabled toggle
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        """Return ``True`` if the strategy is currently active."""
        return self._enabled

    def enable(self) -> None:
        """Allow the strategy to generate signals."""
        if not self._enabled:
            self._enabled = True
            logger.info("Strategy %r enabled.", self._name)

    def disable(self) -> None:
        """
        Prevent the strategy from generating new signals.

        Already-open positions managed by this strategy are not
        automatically closed; that responsibility lies with the engine
        or risk manager.
        """
        if self._enabled:
            self._enabled = False
            logger.info("Strategy %r disabled.", self._name)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Unique strategy name (read-only)."""
        return self._name

    @property
    def instruments(self) -> list[str]:
        """Instrument symbols this strategy trades."""
        return list(self._instruments)

    @property
    def timeframe(self) -> str:
        """Primary candle resolution."""
        return self._timeframe

    @property
    def settings(self) -> Settings:
        """Application settings (read-only reference)."""
        return self._settings

    @property
    def required_history(self) -> int:
        """
        Minimum number of completed candles needed before the strategy
        can produce a valid signal.

        The engine uses this value to skip ``on_candle`` calls until
        enough history has accumulated.  Override in concrete subclasses
        to reflect the actual indicator warm-up requirements.

        Default: ``200`` bars.
        """
        return 200

    # ------------------------------------------------------------------
    # Optional hooks (concrete classes may override)
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """
        Called once by the engine just before the first ``on_candle`` call.

        Override to perform one-time initialisation (load ML models,
        pre-compute static values, open database connections, etc.).
        """

    def on_stop(self) -> None:
        """
        Called once by the engine during graceful shutdown.

        Override to release resources (close file handles, flush caches).
        """

    def on_fill(self, order_id: str, filled_price: float, quantity: float) -> None:
        """
        Notification that an order generated by this strategy was filled.

        Override to update internal state (e.g. track entry price for
        dynamic stop management).

        Parameters
        ----------
        order_id:
            System-level order ID.
        filled_price:
            Actual fill price.
        quantity:
            Filled quantity (always positive; direction is on the Order).
        """

    # ------------------------------------------------------------------
    # Helpers available to concrete strategies
    # ------------------------------------------------------------------

    def _log(self, level: int, msg: str, *args: object) -> None:
        """Emit a log message prefixed with the strategy name."""
        logger.log(level, f"[{self._name}] {msg}", *args)

    def _is_warmed_up(self, df: pd.DataFrame) -> bool:
        """
        Return ``True`` if *df* has at least :attr:`required_history` rows.

        Concrete strategies can call this guard at the top of
        ``on_candle`` to avoid computing indicators on insufficient data.
        """
        return len(df) >= self.required_history

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        status = "enabled" if self._enabled else "disabled"
        return (
            f"<{self.__class__.__name__} "
            f"name={self._name!r} "
            f"timeframe={self._timeframe!r} "
            f"status={status}>"
        )
