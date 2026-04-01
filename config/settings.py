from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------
    # Trading mode
    # -----------------------------------------------------------------
    trading_mode: Literal["paper", "live", "backtest"] = "paper"

    # -----------------------------------------------------------------
    # Dashboard auth
    # -----------------------------------------------------------------
    dashboard_api_token: str = "change_me_to_something_secure"

    # -----------------------------------------------------------------
    # Tradovate (futures + commodities)
    # -----------------------------------------------------------------
    tradovate_username: str = ""
    tradovate_password: str = ""
    tradovate_app_id: str = ""
    tradovate_app_version: str = "1.0"
    tradovate_demo: bool = True

    # -----------------------------------------------------------------
    # OANDA (forex)
    # -----------------------------------------------------------------
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_environment: Literal["practice", "live"] = "practice"

    # -----------------------------------------------------------------
    # Interactive Brokers (options)
    # -----------------------------------------------------------------
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1

    # -----------------------------------------------------------------
    # News & Sentiment
    # -----------------------------------------------------------------
    newsapi_key: str = ""
    alphavantage_api_key: str = ""

    # -----------------------------------------------------------------
    # Risk limits
    # -----------------------------------------------------------------
    daily_loss_limit_pct: float = 3.0
    max_drawdown_pct: float = 10.0
    per_trade_risk_pct: float = 1.5
    allow_overnight_futures: bool = False

    # -----------------------------------------------------------------
    # Paper trading
    # -----------------------------------------------------------------
    paper_initial_capital: float = 100_000.0

    # -----------------------------------------------------------------
    # Dashboard server
    # -----------------------------------------------------------------
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
