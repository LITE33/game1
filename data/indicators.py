"""
data/indicators.py
==================
Thin, consistently-named wrapper functions around pandas-ta.

All functions accept a DataFrame with at minimum these OHLCV columns:

    open, high, low, close, volume

and return either a ``pd.Series`` or a ``pd.DataFrame``.

Column names in return values are taken directly from pandas-ta output
so they stay consistent with the rest of the pandas-ta ecosystem.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_ohlcv(df: pd.DataFrame) -> None:
    """Raise ValueError if the mandatory OHLCV columns are missing."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with lower-cased column names."""
    return df.rename(columns=str.lower)


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def ema(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Exponential Moving Average.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        EMA lookback period.

    Returns
    -------
    pd.Series
        EMA values indexed the same as *df*.
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.ema(d["close"], length=period)
    result.name = f"EMA_{period}"
    return result


def sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Simple Moving Average.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        SMA lookback period.

    Returns
    -------
    pd.Series
        SMA values indexed the same as *df*.
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.sma(d["close"], length=period)
    result.name = f"SMA_{period}"
    return result


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        ATR lookback period.

    Returns
    -------
    pd.Series
        ATR values.
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.atr(d["high"], d["low"], d["close"], length=period)
    result.name = f"ATR_{period}"
    return result


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Average Directional Index with +DI and -DI.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        ADX lookback period.

    Returns
    -------
    pd.DataFrame
        Columns: ``ADX_<period>``, ``DMP_<period>``, ``DMN_<period>``
        (pandas-ta naming convention).
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.adx(d["high"], d["low"], d["close"], length=period)
    return result


def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    """
    Bollinger Bands.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        Rolling window length.
    std:
        Number of standard deviations for the upper/lower bands.

    Returns
    -------
    pd.DataFrame
        Columns (pandas-ta naming):
        ``BBL_<period>_<std>``   – lower band
        ``BBM_<period>_<std>``   – middle band (SMA)
        ``BBU_<period>_<std>``   – upper band
        ``BBB_<period>_<std>``   – bandwidth  ((BBU-BBL)/BBM * 100)
        ``BBP_<period>_<std>``   – percent    ((close-BBL)/(BBU-BBL))
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.bbands(d["close"], length=period, std=std)
    return result


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        RSI lookback period.

    Returns
    -------
    pd.Series
        RSI values in the range [0, 100].
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.rsi(d["close"], length=period)
    result.name = f"RSI_{period}"
    return result


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    Moving Average Convergence Divergence.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    fast:
        Fast EMA period.
    slow:
        Slow EMA period.
    signal:
        Signal line EMA period.

    Returns
    -------
    pd.DataFrame
        Columns (pandas-ta naming):
        ``MACD_<fast>_<slow>_<signal>``   – MACD line
        ``MACDh_<fast>_<slow>_<signal>``  – histogram (MACD - signal)
        ``MACDs_<fast>_<slow>_<signal>``  – signal line
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    result = ta.macd(d["close"], fast=fast, slow=slow, signal=signal)
    return result


# ---------------------------------------------------------------------------
# Volume-weighted
# ---------------------------------------------------------------------------

def vwap(df: pd.DataFrame) -> pd.Series:
    """
    Intraday Volume-Weighted Average Price (VWAP).

    Computed as the cumulative sum of (typical_price * volume) divided by
    the cumulative volume.  Typical price = (high + low + close) / 3.

    Note: this is a *session* VWAP that accumulates from the first row of
    *df*.  For a proper intraday reset, pass only the current session's
    bars.

    Parameters
    ----------
    df:
        OHLCV DataFrame.

    Returns
    -------
    pd.Series
        VWAP values indexed the same as *df*.
    """
    _require_ohlcv(df)
    d = _normalise_columns(df)
    typical = (d["high"] + d["low"] + d["close"]) / 3.0
    cum_tp_vol = (typical * d["volume"]).cumsum()
    cum_vol = d["volume"].cumsum()
    result = cum_tp_vol / cum_vol
    result.name = "VWAP"
    return result


# ---------------------------------------------------------------------------
# Composite / ratio indicators
# ---------------------------------------------------------------------------

def atr_ratio(
    df: pd.DataFrame,
    period: int = 14,
    lookback: int = 100,
) -> pd.Series:
    """
    ATR Ratio: current ATR relative to its rolling mean.

    Defined as::

        ATR(period) / ATR(period).rolling(lookback).mean()

    A value > 1.0 means volatility is above its recent average
    (expanding volatility); < 1.0 means contracting volatility.

    Parameters
    ----------
    df:
        OHLCV DataFrame.
    period:
        ATR calculation period.
    lookback:
        Rolling window over which the ATR mean is computed.

    Returns
    -------
    pd.Series
        ATR ratio values.
    """
    _require_ohlcv(df)
    raw_atr = atr(df, period=period)
    rolling_mean = raw_atr.rolling(window=lookback, min_periods=1).mean()
    result = raw_atr / rolling_mean
    result.name = f"ATR_RATIO_{period}_{lookback}"
    return result
