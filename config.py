from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram Bot
    bot_token: str

    # Database
    database_url: str

    # Redis
    redis_url: str

    # FX Rates API
    fx_api_key: str
    fx_api_url: str = "https://v6.exchangerate-api.com/v6"

    # Bot Settings
    default_currency: str = "RSD"
    supported_currencies: str = "RSD,EUR,USD,CHF,GBP"

    # Timezone
    timezone: str = "Europe/Belgrade"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def currencies_list(self) -> List[str]:
        """Return list of supported currencies"""
        return [c.strip() for c in self.supported_currencies.split(",")]


settings = Settings()