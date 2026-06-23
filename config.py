# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    TWELVEDATA_API_KEY: str = Field(...)
    OLLAMA_API_KEYS_RAW: str = Field("", validation_alias="OLLAMA_API_KEYS")
    OLLAMA_MODEL: str = Field("minimax-m2.5:cloud")
    DATABASE_PATH: str = Field("data/xau_rag_db")
    LIVE_LEDGER_PATH: str = Field("data/live_omni_ledger.csv")
    BACKTEST_LEDGER_PATH: str = Field("data/omni_ledger.csv")

    @property
    def OLLAMA_API_KEYS(self) -> List[str]:
        cleaned = self.OLLAMA_API_KEYS_RAW.replace('"', '').replace("'", "")
        return [k.strip() for k in cleaned.split(",") if k.strip()]

    # Migrate class-based config to modern V2 SettingsConfigDict
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()