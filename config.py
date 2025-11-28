"""
Configuration module for HyperTracker Bot.
Loads environment variables and provides application settings.
"""
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Telegram Bot Configuration
    bot_token: str
    
    # Database Configuration
    database_path: str = "./data/hypertracker.db"
    
    # WebSocket Configuration
    hyperliquid_ws_url: str = "wss://api.hyperliquid.xyz/ws"
    hyperliquid_rest_url: str = "https://api.hyperliquid.xyz/info"
    chaos_labs_ws_url: str = "wss://data.chaoslabs.xyz/ws/liquidations"
    
    # Performance Settings
    ws_reconnect_delay: int = 1
    ws_max_reconnect_delay: int = 60
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10
    
    # Logging
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()


# Create data directory if it doesn't exist
def ensure_data_directory():
    """Ensure the data directory exists for the database."""
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
