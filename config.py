from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    telegram_bot_token: str = ""

    openmodel_api_key: str = ""
    openmodel_base_url: str = "https://api.openmodel.ai"
    analysis_model: str = "deepseek-v4-flash"
    ensemble_models: str = "deepseek-v4-flash,deepseek-v4-pro,claude-sonnet-4-6"
    min_ensemble_agreement: int = 2

    binance_testnet_api_key: Optional[str] = None
    binance_testnet_secret: Optional[str] = None

    alpaca_api_key: Optional[str] = None
    alpaca_secret_key: Optional[str] = None
    alpaca_paper: bool = True

    max_position_size_pct: float = 10.0
    max_daily_trades: int = 5
    stop_loss_pct: float = 5.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
