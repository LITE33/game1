from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from models import Candle, Order, Position


class BrokerBase(ABC):
    """Abstract base class that every broker adapter must implement.

    All network I/O is async so that multiple brokers can be polled
    concurrently inside the event loop.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable broker name, e.g. 'tradovate', 'oanda', 'ibkr'."""

    @property
    @abstractmethod
    def supported_instruments(self) -> list[str]:
        """Return the list of instrument symbols this adapter can trade."""

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
        """Fetch *count* completed candles for *instrument* at *timeframe*.

        Args:
            instrument: Symbol string as used by this broker (e.g. 'EUR_USD').
            timeframe:  Normalised timeframe string ('1m', '5m', '15m', '1h',
                        '4h', '1d').
            count:      Number of completed bars to retrieve (most recent first
                        in the broker response; implementors should return them
                        in ascending chronological order).

        Returns:
            List of :class:`Candle` objects in ascending time order.
        """

    # ------------------------------------------------------------------
    # Account & position queries
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return all currently open positions on this broker account."""

    @abstractmethod
    async def get_account_equity(self) -> float:
        """Return the current net liquidation value (equity) of the account."""

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Submit *order* to the broker.

        The returned :class:`Order` must have its ``broker_order_id`` and
        ``status`` fields updated to reflect the broker's acknowledgement.
        For market orders that fill immediately the returned order should
        have ``status=FILLED`` and ``filled_price`` / ``filled_quantity``
        populated.

        Args:
            order: The order to submit.  Must not be mutated in-place;
                   return a copy (or the same object with updated fields).

        Returns:
            Updated :class:`Order` reflecting current broker state.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Request cancellation of *order_id*.

        Args:
            order_id: The internal (system) order id.

        Returns:
            ``True`` if the cancellation request was accepted by the broker,
            ``False`` otherwise (e.g. order already filled).
        """

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    @abstractmethod
    async def close_position(self, instrument: str) -> bool:
        """Close the open position for *instrument* at market.

        Args:
            instrument: Symbol whose position should be closed.

        Returns:
            ``True`` if the close order was accepted, ``False`` otherwise.
        """

    @abstractmethod
    async def close_all_positions(self) -> bool:
        """Close every open position on this broker account at market.

        Returns:
            ``True`` if all close orders were accepted, ``False`` if any
            failed.  Implementors should attempt to close each position
            individually and aggregate the results.
        """
