import re

from pydantic import Field
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
    ai_internal_api_key: str = ""
    ai_schema_version: str = "ai-response-v1"
    ai_prompt_version: str = "cv-prompts-v1"

    app_env: str = "development"
    app_version: str = "0.1.0"
    app_commit: str = "unknown"
    log_level: str = "INFO"
    api_prefix: str = "/v1"
    ai_rate_limit_per_minute: int = Field(default=60, ge=1, le=600)

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

    def readiness_errors(self) -> list[str]:
        missing: list[str] = []
        fields_set = self.model_fields_set
        provider = self.llm_provider.strip().lower()
        if self.is_production and "llm_provider" not in fields_set:
            missing.append("LLM_PROVIDER")
        if provider not in {"groq", "mock"}:
            missing.append("LLM_PROVIDER")
        if self.is_production and provider != "groq":
            missing.append("LLM_PROVIDER must be groq")
        if self.is_production and self.mock_llm:
            missing.append("MOCK_LLM must be false")
        if provider == "groq" and not self.groq_api_key.strip():
            missing.append("GROQ_API_KEY")
        if self.is_production and "groq_api_key" not in fields_set:
            missing.append("GROQ_API_KEY")

        required_models = {
            "GROQ_MODEL": ("groq_model", self.groq_model),
            "GROQ_EXTRACT_MODEL": ("groq_extract_model", self.groq_extract_model),
            "GROQ_ANALYZE_MODEL": ("groq_analyze_model", self.groq_analyze_model),
            "GROQ_FALLBACK_MODEL": ("groq_fallback_model", self.groq_fallback_model),
        }
        for env_name, (field_name, value) in required_models.items():
            if not value.strip() or self.is_production and field_name not in fields_set:
                missing.append(env_name)

        if self.is_production:
            if "ai_internal_api_key" not in fields_set or not self.ai_internal_api_key.strip():
                missing.append("AI_INTERNAL_API_KEY")
            elif len(self.ai_internal_api_key.strip()) < 32:
                missing.append("AI_INTERNAL_API_KEY must contain at least 32 characters")
            if "app_version" not in fields_set or not self.app_version.strip():
                missing.append("APP_VERSION")
            if "app_commit" not in fields_set or not re.fullmatch(r"[0-9a-fA-F]{7,40}", self.app_commit):
                missing.append("APP_COMMIT must be a Git SHA")
            if "ai_schema_version" not in fields_set or self.ai_schema_version != "ai-response-v1":
                missing.append("AI_SCHEMA_VERSION must be ai-response-v1")
            if "ai_prompt_version" not in fields_set or not self.ai_prompt_version.strip():
                missing.append("AI_PROMPT_VERSION")
            if "mock_llm" not in fields_set:
                missing.append("MOCK_LLM must be explicitly set to false")
            if "api_prefix" not in fields_set or self.api_prefix != "/v1":
                missing.append("API_PREFIX must be /v1")

        return list(dict.fromkeys(missing))

    def validate_production_config(self) -> None:
        if not self.is_production:
            return
        missing = self.readiness_errors()
        if missing:
            raise RuntimeError("Invalid production configuration: " + "; ".join(missing))


settings = Settings()
