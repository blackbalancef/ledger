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

    # Backup Settings
    backup_local_path: str = "./backups"
    backup_s3_enabled: bool = False
    backup_s3_bucket: str = ""
    backup_s3_region: str = "eu-central-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # Support legacy variable names
    aws_access_key: str = ""  # Legacy name (for compatibility)
    aws_secret_key: str = ""   # Legacy name (for compatibility)
    backup_schedule_cron: str = "0 3 * * *"  # 3 AM daily
    
    @property
    def effective_aws_access_key_id(self) -> str:
        """Get AWS access key ID from either standard or legacy variable."""
        return self.aws_access_key_id or self.aws_access_key
    
    @property
    def effective_aws_secret_access_key(self) -> str:
        """Get AWS secret access key from either standard or legacy variable."""
        return self.aws_secret_access_key or self.aws_secret_key

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