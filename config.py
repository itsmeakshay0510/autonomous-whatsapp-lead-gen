"""
PHN Technology - WhatsApp Agent Configuration
Centralized configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- WhatsApp Business API ---
    whatsapp_verify_token: str = "REPLACE_YOUR_VERIFY_TOKEN"
    whatsapp_access_token: str = "REPLACE_YOUR_ACCESS_TOKEN"
    whatsapp_phone_number_id: str = "REPLACE_YOUR_PHONE_NUMBER_ID"
    whatsapp_business_account_id: str = "REPLACE_YOUR_BUSINESS_ACCOUNT_ID"
    whatsapp_api_version: str = "v21.0"

    # --- Ollama LLM ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    ollama_keep_alive: int = -1
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_temperature: float = 0.7

    # --- Server ---
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # --- Cache ---
    cache_similarity_threshold: float = 0.90
    cache_max_size: int = 5000

    # --- Memory ---
    max_conversation_turns: int = 20

    # --- Paths ---
    data_dir: str = "data"
    db_path: str = "database/phn_agent.db"

    @property
    def whatsapp_api_url(self) -> str:
        return f"https://graph.facebook.com/{self.whatsapp_api_version}/{self.whatsapp_phone_number_id}/messages"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
