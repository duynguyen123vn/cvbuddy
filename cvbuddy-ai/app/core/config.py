from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "groq"  # groq | mock
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    groq_extract_model: str = "qwen/qwen3.8-27b"
    groq_analyze_model: str = "qwen/qwen3.8-27b"
    groq_fallback_model: str = "openai/gpt-oss-120b"
    mock_llm: bool = False
    ai_internal_key: str = ""
    ai_schema_version: str = "1.0.0"
    ai_prompt_version: str = "cv-prompts-v1"

    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/v1"

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def use_mock_llm(self) -> bool:
        provider = (self.llm_provider or "groq").strip().lower()
        if self.mock_llm or provider == "mock":
            return True
        if provider == "groq":
            return not self.groq_api_key.strip()
        return True

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}

    def validate_production_config(self) -> None:
        if not self.is_production:
            return

        missing = []
        if self.llm_provider.strip().lower() != "groq":
            missing.append("LLM_PROVIDER must be groq")
        if not self.groq_api_key.strip():
            missing.append("GROQ_API_KEY is required")
        if not self.groq_model.strip():
            missing.append("GROQ_MODEL is required")
        if self.mock_llm:
            missing.append("MOCK_LLM must be false")
        if not self.groq_extract_model.strip():
            missing.append("GROQ_EXTRACT_MODEL is required")
        if not self.groq_analyze_model.strip():
            missing.append("GROQ_ANALYZE_MODEL is required")
        if not self.groq_fallback_model.strip():
            missing.append("GROQ_FALLBACK_MODEL is required")
        if not self.ai_internal_key.strip():
            missing.append("AI_INTERNAL_KEY is required")
        elif len(self.ai_internal_key.strip()) < 32:
            missing.append("AI_INTERNAL_KEY must contain at least 32 characters")
        if self.api_prefix != "/v1":
            missing.append("API_PREFIX must be /v1")
        if missing:
            raise RuntimeError("Invalid production configuration: " + "; ".join(missing))


settings = Settings()
