"""
config/settings.py
==================
Centralised application settings loaded from environment variables / .env file.

Usage
-----
    from config.settings import get_settings

    settings = get_settings()          # cached singleton
    print(settings.TRADING_MODE)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All runtime-configurable parameters for the trading system.

    Values are read (in order of precedence) from:
      1. Real environment variables
      2. A `.env` file in the working directory
      3. The default values defined below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Global mode
    # ------------------------------------------------------------------
    TRADING_MODE: Literal["paper", "live", "backtest"] = Field(
        default="paper",
        description="Execution mode: paper | live | backtest",
    )

    # ------------------------------------------------------------------
    # Dashboard security
    # ------------------------------------------------------------------
    DASHBOARD_API_TOKEN: str = Field(
        default="change_me_to_something_secure",
        description="Bearer token that protects the dashboard REST API.",
    )

    # ------------------------------------------------------------------
    # Tradovate (futures + commodities)
    # ------------------------------------------------------------------
    TRADOVATE_USERNAME: str = Field(default="", description="Tradovate account username.")
    TRADOVATE_PASSWORD: str = Field(default="", description="Tradovate account password.")
    TRADOVATE_APP_ID: str = Field(default="", description="Tradovate application ID.")
    TRADOVATE_APP_VERSION: str = Field(default="1.0", description="Tradovate application version.")
    TRADOVATE_DEMO: bool = Field(
        default=True,
        description="Connect to Tradovate demo/simulation environment when True.",
    )

    # ------------------------------------------------------------------
    # OANDA (forex)
    # ------------------------------------------------------------------
    OANDA_API_KEY: str = Field(default="", description="OANDA v20 REST API key.")
    OANDA_ACCOUNT_ID: str = Field(default="", description="OANDA account identifier.")
    OANDA_ENVIRONMENT: Literal["practice", "live"] = Field(
        default="practice",
        description="OANDA environment: practice | live",
    )

    # ------------------------------------------------------------------
    # Interactive Brokers (options)
    # ------------------------------------------------------------------
    IBKR_HOST: str = Field(default="127.0.0.1", description="TWS / IB Gateway host.")
    IBKR_PORT: int = Field(default=7497, description="TWS / IB Gateway port (paper=7497, live=7496).")
    IBKR_CLIENT_ID: int = Field(default=1, description="IB client ID for this connection.")

    # ------------------------------------------------------------------
    # News & Sentiment data providers
    # ------------------------------------------------------------------
    NEWSAPI_KEY: str = Field(default="", description="NewsAPI.org API key.")
    ALPHAVANTAGE_API_KEY: str = Field(default="", description="Alpha Vantage API key.")

    # ------------------------------------------------------------------
    # Risk management limits
    # ------------------------------------------------------------------
    DAILY_LOSS_LIMIT_PCT: float = Field(
        default=3.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed daily loss as a percentage of starting equity.",
    )
    MAX_DRAWDOWN_PCT: float = Field(
        default=10.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed peak-to-trough drawdown before halting trading.",
    )
    PER_TRADE_RISK_PCT: float = Field(
        default=1.5,
        ge=0.0,
        le=100.0,
        description="Maximum risk per trade as a percentage of current equity.",
    )
    ALLOW_OVERNIGHT_FUTURES: bool = Field(
        default=False,
        description="Whether futures positions may be held through the overnight session.",
    )

    # ------------------------------------------------------------------
    # Paper trading
    # ------------------------------------------------------------------
    PAPER_INITIAL_CAPITAL: float = Field(
        default=100_000.0,
        gt=0.0,
        description="Starting virtual capital for paper-trading mode.",
    )

    # ------------------------------------------------------------------
    # Dashboard server
    # ------------------------------------------------------------------
    DASHBOARD_HOST: str = Field(default="0.0.0.0", description="Host/interface the dashboard binds to.")
    DASHBOARD_PORT: int = Field(default=8080, description="TCP port for the dashboard server.")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def is_paper(self) -> bool:
        return self.TRADING_MODE == "paper"

    @property
    def is_live(self) -> bool:
        return self.TRADING_MODE == "live"

    @property
    def is_backtest(self) -> bool:
        return self.TRADING_MODE == "backtest"

    @property
    def oanda_base_url(self) -> str:
        if self.OANDA_ENVIRONMENT == "live":
            return "https://api-fxtrade.oanda.com"
        return "https://api-fxpractice.oanda.com"

    @property
    def tradovate_base_url(self) -> str:
        if self.TRADOVATE_DEMO:
            return "https://demo.tradovateapi.com/v1"
        return "https://live.tradovateapi.com/v1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application-wide Settings singleton.

    The result is cached after the first call so the .env file is only
    parsed once per process lifetime.  Call ``get_settings.cache_clear()``
    in tests to force a fresh read.
    """
    return Settings()
