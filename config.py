"""
Configuration management for the Spike AI application.
Loads environment variables and provides application settings.
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional, Any
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    litellm_api_key: Optional[str] = None
    litellm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    llm_model: str = "gpt-4"
    llm_fallback_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2000
    llm_timeout: int = 30
    
    google_application_credentials: str = "credentials.json"
    
    screaming_frog_sheet_id: str
    screaming_frog_sheet_name: Optional[str] = None
    
    port: int = 8080
    host: str = "0.0.0.0"
    log_level: str = "DEBUG"
    
    ga4_api_timeout: int = 30
    sheets_api_timeout: int = 30
    
    @model_validator(mode='before')
    @classmethod
    def strip_quotes_from_strings(cls, data: Any) -> Any:
        """Strip surrounding quotes from string values in .env file."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        data[key] = value[1:-1]
        return data
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings


def init_google_credentials():
    """Initialize Google credentials from environment."""
    settings = get_settings()
    credentials_path = settings.google_application_credentials
    
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Google credentials file not found at: {credentials_path}. "
            "Please ensure credentials.json is in the project root."
        )
    
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    
    return credentials_path

