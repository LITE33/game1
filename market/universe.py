"""
market/universe.py
==================
Canonical definitions of every tradeable instrument in the system.

Each entry in ``UNIVERSE`` maps an instrument *symbol* (str) to an
``Instrument`` dataclass that carries all the metadata needed by the
position sizer, risk manager, and broker adapters.

Session times are expressed in Eastern Time (ET) as ``"HH:MM"`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Instrument:
    """All static metadata for a single tradeable instrument."""

    symbol: str
    name: str
    market_type: str          # "futures" | "forex" | "options" | "commodity"
    broker: str               # "tradovate" | "oanda" | "ibkr"
    tick_size: float          # smallest price increment
    tick_value: float         # USD value of one tick move
    contract_size: float      # units per contract (shares, oz, bbls, …)
    currency: str             # settlement currency
    sessions: list[tuple[str, str]] = field(default_factory=list)
    # Each tuple is (open_time_ET, close_time_ET) in "HH:MM" format.
    overnight_allowed: bool = False


# ---------------------------------------------------------------------------
# Instrument definitions
# ---------------------------------------------------------------------------

UNIVERSE: dict[str, Instrument] = {

    # -----------------------------------------------------------------------
    # Micro Futures  (via Tradovate)
    # -----------------------------------------------------------------------

    "MES": Instrument(
        symbol="MES",
        name="Micro E-mini S&P 500",
        market_type="futures",
        broker="tradovate",
        tick_size=0.25,
        tick_value=1.25,        # $1.25 per tick  (0.25 index pts × $5 multiplier)
        contract_size=5.0,      # $5 × index level
        currency="USD",
        sessions=[("09:30", "16:00")],
        overnight_allowed=False,
    ),

    "MNQ": Instrument(
        symbol="MNQ",
        name="Micro E-mini Nasdaq-100",
        market_type="futures",
        broker="tradovate",
        tick_size=0.25,
        tick_value=0.50,        # $0.50 per tick  (0.25 pts × $2 multiplier)
        contract_size=2.0,
        currency="USD",
        sessions=[("09:30", "16:00")],
        overnight_allowed=False,
    ),

    "MGC": Instrument(
        symbol="MGC",
        name="Micro Gold",
        market_type="futures",
        broker="tradovate",
        tick_size=0.10,
        tick_value=1.00,        # $1.00 per tick  (0.10 $/oz × 10 oz)
        contract_size=10.0,     # 10 troy oz
        currency="USD",
        sessions=[("18:00", "17:00")],   # Sunday–Friday nearly 24-hour
        overnight_allowed=True,
    ),

    "MCL": Instrument(
        symbol="MCL",
        name="Micro Crude Oil",
        market_type="futures",
        broker="tradovate",
        tick_size=0.01,
        tick_value=1.00,        # $1.00 per tick  (0.01 $/bbl × 100 bbl)
        contract_size=100.0,    # 100 barrels
        currency="USD",
        sessions=[("18:00", "17:00")],
        overnight_allowed=True,
    ),

    # -----------------------------------------------------------------------
    # Standard Futures / Commodities  (via Tradovate — full-size contracts)
    # -----------------------------------------------------------------------

    "GC": Instrument(
        symbol="GC",
        name="Gold (Full-size)",
        market_type="commodity",
        broker="tradovate",
        tick_size=0.10,
        tick_value=10.00,       # $10 per tick  (0.10 $/oz × 100 oz)
        contract_size=100.0,    # 100 troy oz
        currency="USD",
        sessions=[("18:00", "17:00")],
        overnight_allowed=True,
    ),

    "CL": Instrument(
        symbol="CL",
        name="Crude Oil WTI (Full-size)",
        market_type="commodity",
        broker="tradovate",
        tick_size=0.01,
        tick_value=10.00,       # $10 per tick  (0.01 $/bbl × 1000 bbl)
        contract_size=1000.0,   # 1,000 barrels
        currency="USD",
        sessions=[("18:00", "17:00")],
        overnight_allowed=True,
    ),

    # -----------------------------------------------------------------------
    # Forex  (via OANDA)
    # -----------------------------------------------------------------------

    "EUR_USD": Instrument(
        symbol="EUR_USD",
        name="Euro / US Dollar",
        market_type="forex",
        broker="oanda",
        tick_size=0.00001,      # 0.1 pip
        tick_value=0.10,        # ~$0.10 per pip per 10k notional
        contract_size=10_000.0, # standard lot = 100k; mini = 10k
        currency="USD",
        sessions=[("00:00", "23:59")],   # 24-hour Mon–Fri
        overnight_allowed=True,
    ),

    "GBP_USD": Instrument(
        symbol="GBP_USD",
        name="British Pound / US Dollar",
        market_type="forex",
        broker="oanda",
        tick_size=0.00001,
        tick_value=0.10,
        contract_size=10_000.0,
        currency="USD",
        sessions=[("00:00", "23:59")],
        overnight_allowed=True,
    ),

    "USD_JPY": Instrument(
        symbol="USD_JPY",
        name="US Dollar / Japanese Yen",
        market_type="forex",
        broker="oanda",
        tick_size=0.001,        # 0.1 pip (JPY pair)
        tick_value=0.10,
        contract_size=10_000.0,
        currency="JPY",
        sessions=[("00:00", "23:59")],
        overnight_allowed=True,
    ),

    "USD_CAD": Instrument(
        symbol="USD_CAD",
        name="US Dollar / Canadian Dollar",
        market_type="forex",
        broker="oanda",
        tick_size=0.00001,
        tick_value=0.10,
        contract_size=10_000.0,
        currency="CAD",
        sessions=[("00:00", "23:59")],
        overnight_allowed=True,
    ),

    # -----------------------------------------------------------------------
    # Options underlyings  (via Interactive Brokers)
    # -----------------------------------------------------------------------

    "SPX": Instrument(
        symbol="SPX",
        name="S&P 500 Index (options underlying)",
        market_type="options",
        broker="ibkr",
        tick_size=0.05,
        tick_value=0.05,        # cash-settled; 1 index pt = $100 on SPX options
        contract_size=100.0,    # 100× multiplier
        currency="USD",
        sessions=[("09:30", "16:15")],
        overnight_allowed=False,
    ),

    "QQQ": Instrument(
        symbol="QQQ",
        name="Invesco QQQ Trust (options underlying)",
        market_type="options",
        broker="ibkr",
        tick_size=0.01,
        tick_value=1.00,        # 1 contract = 100 shares; $0.01 × 100 = $1
        contract_size=100.0,
        currency="USD",
        sessions=[("09:30", "16:00")],
        overnight_allowed=False,
    ),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_instrument(symbol: str) -> Instrument:
    """
    Look up an instrument by its symbol.

    Parameters
    ----------
    symbol:
        The instrument's canonical symbol key, e.g. ``"EUR_USD"``.

    Returns
    -------
    Instrument

    Raises
    ------
    KeyError
        If *symbol* is not found in ``UNIVERSE``.
    """
    try:
        return UNIVERSE[symbol]
    except KeyError:
        raise KeyError(
            f"Instrument {symbol!r} not found in UNIVERSE. "
            f"Available symbols: {sorted(UNIVERSE)}"
        )


def get_instruments_by_broker(broker: str) -> list[Instrument]:
    """
    Return all instruments handled by a specific broker.

    Parameters
    ----------
    broker:
        Broker identifier, e.g. ``"oanda"``, ``"tradovate"``, ``"ibkr"``.

    Returns
    -------
    list[Instrument]
        May be empty if the broker is not used by any instrument.
    """
    return [inst for inst in UNIVERSE.values() if inst.broker == broker]


def get_instruments_by_type(market_type: str) -> list[Instrument]:
    """
    Return all instruments of a given market type.

    Parameters
    ----------
    market_type:
        One of ``"futures"``, ``"forex"``, ``"options"``, ``"commodity"``.

    Returns
    -------
    list[Instrument]
    """
    return [inst for inst in UNIVERSE.values() if inst.market_type == market_type]
