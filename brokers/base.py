"""
brokers/base.py
===============
Abstract base class that every broker adapter must implement.

All methods are async to allow non-blocking I/O across different
broker SDKs (REST, WebSocket, TWS API, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from models import Candle, Order, Position


class BrokerBase(ABC):
    """
    Common interface for all broker integrations.

    Concrete subclasses live in brokers/<name>.py and handle the
    translation between this generic API and each broker's specific
    protocol (REST, FIX, native SDK, etc.).
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this broker, e.g. ``"oanda"``, ``"tradovate"``."""

    @property
    @abstractmethod
    def supported_instruments(self) -> list[str]:
        """
        List of instrument symbols this broker adapter can trade.

        Symbols must match the keys used in ``market.universe.UNIVERSE``.
        Example: ``["EUR_USD", "GBP_USD", "USD_JPY"]``
        """

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_candles(
        self,
        instrument: str,
        timeframe: str,
        count: int,
    ) -> list[Candle]:
        """
        Fetch historical OHLCV bars from the broker.

        Parameters
        ----------
        instrument:
            Symbol string, e.g. ``"EUR_USD"`` or ``"MES"``.
        timeframe:
            Granularity string used across the whole system,
            e.g. ``"1m"``, ``"5m"``, ``"15m"``, ``"1h"``, ``"4h"``, ``"1d"``.
        count:
            Number of completed bars to return (most recent ``count`` bars).

        Returns
        -------
        list[Candle]
            Bars in chronological order (oldest first).
        """

    # ------------------------------------------------------------------
    # Account / positions
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """
        Return all currently open positions held at this broker.

        Returns
        -------
        list[Position]
            Empty list if no positions are open.
        """

    @abstractmethod
    async def get_account_equity(self) -> float:
        """
        Return the current total account equity (NAV) in account currency.

        For paper brokers this should return the simulated equity value.
        """

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """
        Submit an order to the broker.

        The broker adapter must populate ``order.broker_order_id`` and
        update ``order.status`` before returning the mutated ``Order``
        object.  Do *not* raise on soft failures (rejected orders);
        instead set ``order.status = OrderStatus.REJECTED`` and include
        a reason in ``order.metadata["reject_reason"]``.

        Parameters
        ----------
        order:
            The order to submit.  ``order.id`` is already set by the
            caller and should be preserved.

        Returns
        -------
        Order
            The same object with broker-assigned fields populated.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Request cancellation of a pending/submitted order.

        Parameters
        ----------
        order_id:
            The system-level ``Order.id`` (not the broker order ID).

        Returns
        -------
        bool
            ``True`` if the cancellation was acknowledged by the broker,
            ``False`` otherwise (e.g. order already filled).
        """

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    @abstractmethod
    async def close_position(self, instrument: str) -> bool:
        """
        Flatten (fully close) the open position for *instrument*.

        Parameters
        ----------
        instrument:
            Symbol whose position should be closed.

        Returns
        -------
        bool
            ``True`` if the close order was accepted, ``False`` if there
            was no position to close or the request failed.
        """

    @abstractmethod
    async def close_all_positions(self) -> bool:
        """
        Close every open position at this broker simultaneously.

        Used by the emergency stop / daily-loss-limit handler.

        Returns
        -------
        bool
            ``True`` if all close orders were accepted without error.
        """

    # ------------------------------------------------------------------
    # Optional lifecycle hooks (concrete classes may override)
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Establish a connection / authenticate with the broker.

        Called once at startup before any other method.  Default
        implementation is a no-op; override when the broker requires
        an explicit connection step (e.g. TWS socket, OAuth flow).
        """

    async def disconnect(self) -> None:
        """
        Gracefully close the connection to the broker.

        Called during system shutdown.  Default implementation is a no-op.
        """

    async def is_connected(self) -> bool:
        """
        Return whether the adapter currently has an active connection.

        Default implementation always returns ``True`` for brokers that
        use stateless REST APIs.
        """
        return True

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} broker={self.name!r}>"
