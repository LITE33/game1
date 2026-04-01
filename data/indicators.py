"""Technical indicator wrappers around pandas-ta.

All public functions accept a DataFrame with at minimum the columns:
    open, high, low, close, volume

and return either a ``pd.Series`` or a ``pd.DataFrame`` with clearly named
columns.  Column names follow pandas-ta conventions so that callers can
rely on them being stable.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_ohlcv(df: pd.DataFrame) -> None:
    """Raise ValueError if required OHLCV columns are absent."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with lower-case column names."""
    out = df.copy()
    out.columns = out.columns.str.lower()
    return out


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def ema(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Exponential Moving Average.

    Args:
        df:     OHLCV DataFrame.
        period: Lookback period (number of bars).

    Returns:
        pd.Series named ``EMA_{period}``.
    """
    data = _normalise_columns(df)
    result: pd.Series = ta.ema(data["close"], length=period)
    return result


def sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Simple Moving Average.

    Args:
        df:     OHLCV DataFrame.
        period: Lookback period (number of bars).

    Returns:
        pd.Series named ``SMA_{period}``.
    """
    data = _normalise_columns(df)
    result: pd.Series = ta.sma(data["close"], length=period)
    return result


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range.

    Args:
        df:     OHLCV DataFrame.
        period: Lookback period (number of bars).

    Returns:
        pd.Series named ``ATRr_{period}`` (pandas-ta convention).
    """
    data = _normalise_columns(df)
    result: pd.Series = ta.atr(
        data["high"], data["low"], data["close"], length=period
    )
    return result


def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands.

    Args:
        df:     OHLCV DataFrame.
        period: Moving average period.
        std:    Number of standard deviations for the bands.

    Returns:
        pd.DataFrame with columns:
            BBL_{period}_{std}  – lower band
            BBM_{period}_{std}  – middle band (SMA)
            BBU_{period}_{std}  – upper band
            BBB_{period}_{std}  – bandwidth  ((upper - lower) / middle * 100)
            BBP_{period}_{std}  – percent B  ((close - lower) / (upper - lower))
    """
    data = _normalise_columns(df)
    result: pd.DataFrame = ta.bbands(data["close"], length=period, std=std)
    return result


# ---------------------------------------------------------------------------
# Momentum / trend
# ---------------------------------------------------------------------------

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Relative Strength Index.

    Args:
        df:     OHLCV DataFrame.
        period: Lookback period (number of bars).

    Returns:
        pd.Series named ``RSI_{period}``.
    """
    data = _normalise_columns(df)
    result: pd.Series = ta.rsi(data["close"], length=period)
    return result


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence / Divergence.

    Args:
        df:     OHLCV DataFrame.
        fast:   Fast EMA period.
        slow:   Slow EMA period.
        signal: Signal EMA period.

    Returns:
        pd.DataFrame with columns:
            MACD_{fast}_{slow}_{signal}   – MACD line
            MACDh_{fast}_{slow}_{signal}  – histogram (MACD - signal)
            MACDs_{fast}_{slow}_{signal}  – signal line
    """
    data = _normalise_columns(df)
    result: pd.DataFrame = ta.macd(
        data["close"], fast=fast, slow=slow, signal=signal
    )
    return result


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index with +DI and -DI.

    Args:
        df:     OHLCV DataFrame.
        period: Lookback period (number of bars).

    Returns:
        pd.DataFrame with columns:
            ADX_{period}   – average directional index
            DMP_{period}   – +DI (positive directional movement)
            DMN_{period}   – -DI (negative directional movement)
    """
    data = _normalise_columns(df)
    result: pd.DataFrame = ta.adx(
        data["high"], data["low"], data["close"], length=period
    )
    return result


# ---------------------------------------------------------------------------
# Volume-weighted
# ---------------------------------------------------------------------------

def vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday Volume-Weighted Average Price (cumulative, session-based).

    Computed as::

        cumulative_sum(volume * typical_price) / cumulative_sum(volume)

    where ``typical_price = (high + low + close) / 3``.

    Note: For a true intraday VWAP the caller should pass only bars from
    the current trading session.  This function resets at the first bar of
    the DataFrame (i.e. it is cumulative over the entire supplied window).

    Args:
        df: OHLCV DataFrame (must include *volume* column).

    Returns:
        pd.Series named ``VWAP`` aligned with *df*'s index.
    """
    data = _normalise_columns(df)
    typical_price = (data["high"] + data["low"] + data["close"]) / 3.0
    cum_tp_vol = (typical_price * data["volume"]).cumsum()
    cum_vol = data["volume"].cumsum()
    series = cum_tp_vol / cum_vol
    series.name = "VWAP"
    return series


# ---------------------------------------------------------------------------
# Derived / composite
# ---------------------------------------------------------------------------

def atr_ratio(
    df: pd.DataFrame,
    period: int = 14,
    lookback: int = 50,
) -> pd.Series:
    """ATR Ratio: current ATR normalised by its rolling mean.

    Computed as::

        ATR(period) / ATR(period).rolling(lookback).mean()

    A value > 1 indicates above-average volatility; < 1 indicates
    compressed volatility (potential breakout candidate).

    Args:
        df:       OHLCV DataFrame.
        period:   ATR lookback period.
        lookback: Rolling window over which to average the ATR.

    Returns:
        pd.Series named ``ATR_ratio_{period}_{lookback}``.
    """
    raw_atr = atr(df, period=period)
    rolling_mean = raw_atr.rolling(window=lookback).mean()
    ratio = raw_atr / rolling_mean
    ratio.name = f"ATR_ratio_{period}_{lookback}"
    return ratio
