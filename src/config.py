"""Central configuration using pydantic-settings."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Schwab
    schwab_api_key: str = ""
    schwab_app_secret: str = ""
    schwab_callback_url: str = "https://127.0.0.1:8182"
    schwab_token_path: str = "./config/schwab_token.json"
    schwab_account_hash: str = ""

    # LLM
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Crypto payout
    crypto_exchange: str = "binance"
    crypto_exchange_api_key: str = ""
    crypto_exchange_secret: str = ""
    payout_coin: str = "BTC"
    payout_wallet_address: str = ""
    payout_percentage: float = 0.05

    # Risk management
    max_position_size_pct: float = 0.05
    max_total_exposure_pct: float = 0.25
    max_single_loss_pct: float = 0.02
    daily_loss_limit_pct: float = 0.05

    # Arena
    trading_cycle_days: int = 15
    paper_trade: bool = True

    # Data sources
    news_api_key: str = ""
    polygon_api_key: str = ""

    # Database
    db_path: str = "./config/agents_db.sqlite"

    @property
    def token_path(self) -> Path:
        return Path(self.schwab_token_path)

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
