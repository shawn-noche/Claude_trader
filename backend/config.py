from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    log_level: str = "INFO"

    # Ingestion
    fetch_timeout_seconds: int = 15
    max_article_chars: int = 20_000

    # LLM
    claude_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096


settings = Settings()
