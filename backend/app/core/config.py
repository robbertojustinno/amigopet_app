from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AmigoPet V8 REAL"
    ENV: str = "development"
    SECRET_KEY: str = "change-me"
    BACKEND_CORS_ORIGINS: str = "http://localhost:8080,http://127.0.0.1:8080"
    DATABASE_URL: str = "sqlite:///./amigopet.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    DEFAULT_ADDRESS: str = "Rua Mirabel, 49 Piabetá - Magé - RJ CEP 25931-854"
    MERCADO_PAGO_ACCESS_TOKEN: str = ""
    MERCADO_PAGO_PUBLIC_KEY: str = ""

    @property
    def cors_origins(self) -> List[str]:
        return [item.strip() for item in self.BACKEND_CORS_ORIGINS.split(",") if item.strip()]

settings = Settings()
