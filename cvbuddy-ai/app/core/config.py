from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "groq"  # groq | mock
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.6-27b"
    groq_extract_model: str = "qwen/qwen3.6-27b"
    groq_analyze_model: str = "qwen/qwen3.6-27b"
    groq_fallback_model: str = "openai/gpt-oss-120b"
    mock_llm: bool = False

    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/v1"

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def use_mock_llm(self) -> bool:
        if self.mock_llm or self.llm_provider == "mock":
            return True
        if self.llm_provider == "groq":
            return not self.groq_api_key.strip()
        return True


settings = Settings()
