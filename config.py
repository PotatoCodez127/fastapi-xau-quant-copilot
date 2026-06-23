# config.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os

class Settings(BaseSettings):
    TWELVEDATA_API_KEY: str = Field(..., env="TWELVEDATA_API_KEY")
    OLLAMA_API_KEYS_RAW: str = Field("", env="OLLAMA_API_KEYS")
    OLLAMA_MODEL: str = Field("minimax-m2.5:cloud", env="OLLAMA_MODEL")
    DATABASE_PATH: str = Field("data/xau_rag_db", env="DATABASE_PATH")
    LIVE_LEDGER_PATH: str = Field("data/live_omni_ledger.csv", env="LIVE_LEDGER_PATH")
    BACKTEST_LEDGER_PATH: str = Field("data/omni_ledger.csv", env="BACKTEST_LEDGER_PATH")

    @property
    def OLLAMA_API_KEYS(self) -> List[str]:
        cleaned = self.OLLAMA_API_KEYS_RAW.replace('"', '').replace("'", "")
        return [k.strip() for k in cleaned.split(",") if k.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()