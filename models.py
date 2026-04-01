from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"


class MarketRegime(str, Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    RANGING_NORMAL = "RANGING_NORMAL"
    RANGING_COMPRESSED = "RANGING_COMPRESSED"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    BREAKOUT_CANDIDATE = "BREAKOUT_CANDIDATE"
    UNKNOWN = "UNKNOWN"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@dataclass
class Candle:
    """A single OHLCV bar for a given instrument and timeframe."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    instrument: str
    timeframe: str  # e.g. "5m", "1h", "4h", "1d"


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A trading signal produced by a strategy."""

    instrument: str
    direction: Direction
    strategy_name: str
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None
    size_hint: float = 1.0        # multiplier for position sizer (0.0 to 2.0)
    confidence: float = 1.0       # from ML signal enhancer (0.0 to 1.0)
    regime: MarketRegime = MarketRegime.UNKNOWN
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """A broker order derived from a Signal."""

    id: str
    instrument: str
    direction: Direction
    order_type: OrderType
    quantity: float
    price: Optional[float]        # None for market orders
    stop_price: Optional[float]
    status: OrderStatus
    strategy_name: str
    signal: Optional[Signal]
    broker_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """An open position held by the system."""

    instrument: str
    direction: Direction
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: Optional[float]
    strategy_name: str
    opened_at: datetime
    unrealized_pnl: float = 0.0
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trade (closed)
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    """A completed (closed) trade with realised P&L."""

    id: str
    instrument: str
    direction: Direction
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    strategy_name: str
    regime: str
    opened_at: datetime
    closed_at: datetime
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

@dataclass
class SentimentScore:
    """Aggregated news sentiment for a given instrument."""

    instrument: str
    score: float          # -1.0 to +1.0
    article_count: int
    updated_at: datetime
    headlines: list = field(default_factory=list)
