import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["version"]
    assert "commit" in r.json()
    assert r.headers["x-request-id"]


def test_request_id_is_returned_and_reused(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "java-trace-123"})

    assert response.headers["X-Request-ID"] == "java-trace-123"


def test_production_gate_requires_internal_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.pipeline import analyze as analyze_pipeline

    def fail_if_called(**_kwargs):
        raise AssertionError("Provider must not be called before internal authentication")

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ai_internal_api_key", "test-internal-secret")
    monkeypatch.setattr(analyze_pipeline, "get_llm_service", fail_if_called)

    denied = client.get("/v1/industries")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "authentication_required"
    assert denied.headers["X-Request-ID"] == denied.json()["error"]["requestId"]

    analyze_body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    denied_analysis = client.post("/v1/cv/analyze", json=analyze_body)
    assert denied_analysis.status_code == 401

    wrong_key = client.get(
        "/v1/industries",
        headers={"X-AI-Internal-Key": "wrong-secret"},
    )
    assert wrong_key.status_code == 401

    allowed = client.get(
        "/v1/industries",
        headers={"X-AI-Internal-Key": "test-internal-secret"},
    )
    assert allowed.status_code == 200


def test_production_rate_limit_is_keyed_and_returns_retry_after(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from app.core.config import settings

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ai_internal_api_key", "r" * 40)
    monkeypatch.setattr(settings, "ai_rate_limit_per_minute", 1)
    headers = {"X-AI-Internal-Key": "r" * 40}

    first = client.get("/v1/industries", headers=headers)
    second = client.get("/v1/industries", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "request_rate_limited"
    assert second.headers["Retry-After"]
    assert "r" * 40 not in second.text
    assert "r" * 40 not in caplog.text
    assert any(
        getattr(record, "request_id", None) == second.headers["X-Request-ID"]
        for record in caplog.records
    )


def test_legacy_ai_alias_is_removed(client: TestClient) -> None:
    response = client.get("/ai/models")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_production_config_fails_closed() -> None:
    from app.core.config import Settings

    config = Settings(
        _env_file=None,
        app_env="production",
        llm_provider="groq",
        groq_api_key="",
        mock_llm=True,
        ai_internal_api_key="",
    )

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        config.validate_production_config()


def test_production_config_requires_every_explicit_value() -> None:
    from app.core.config import Settings

    config = Settings(
        _env_file=None,
        app_env="production",
        app_version="1.2.3",
        app_commit="a" * 40,
        llm_provider="groq",
        groq_api_key="fake-key-for-config-test",
        groq_model="qwen/qwen3.8-27b",
        groq_extract_model="qwen/qwen3.8-27b",
        groq_analyze_model="qwen/qwen3.8-27b",
        groq_fallback_model="openai/gpt-oss-120b",
        mock_llm=False,
        ai_internal_api_key="x" * 40,
        ai_schema_version="ai-response-v1",
        ai_prompt_version="test-prompts-v1",
        api_prefix="/v1",
    )
    assert config.readiness_errors() == []


def test_production_environment_variable_names_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    environment = {
        "APP_ENV": "production",
        "APP_VERSION": "1.2.3",
        "APP_COMMIT": "b" * 40,
        "LLM_PROVIDER": "groq",
        "MOCK_LLM": "false",
        "GROQ_API_KEY": "synthetic-groq-test-key",
        "AI_INTERNAL_API_KEY": "y" * 40,
        "API_PREFIX": "/v1",
        "GROQ_MODEL": "qwen/qwen3.8-27b",
        "GROQ_EXTRACT_MODEL": "qwen/qwen3.8-27b",
        "GROQ_ANALYZE_MODEL": "qwen/qwen3.8-27b",
        "GROQ_FALLBACK_MODEL": "openai/gpt-oss-120b",
        "AI_SCHEMA_VERSION": "ai-response-v1",
        "AI_PROMPT_VERSION": "test-prompts-v1",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    config = Settings(_env_file=None)
    assert config.ai_internal_api_key == "y" * 40
    assert config.readiness_errors() == []


def test_mock_provider_is_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.services.errors import MockProhibitedError
    from app.services.llm import get_llm_service

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "mock_llm", True)
    with pytest.raises(MockProhibitedError):
        get_llm_service()


def test_ready_endpoint_is_safe_and_respects_config(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "ai_internal_api_key", "do-not-return-this-secret")
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "do-not-return-this-secret" not in response.text

    monkeypatch.setattr(settings, "app_env", "production")
    response = client.get("/ready")
    assert response.status_code == 503
    assert "do-not-return-this-secret" not in response.text


def test_production_ready_succeeds_only_with_complete_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main
    from app.core.config import Settings

    production = Settings(
        _env_file=None,
        app_env="production",
        app_version="1.2.3",
        app_commit="c" * 40,
        llm_provider="groq",
        groq_api_key="synthetic-key",
        groq_model="qwen/qwen3.8-27b",
        groq_extract_model="qwen/qwen3.8-27b",
        groq_analyze_model="qwen/qwen3.8-27b",
        groq_fallback_model="openai/gpt-oss-120b",
        mock_llm=False,
        ai_internal_api_key="z" * 40,
        ai_schema_version="ai-response-v1",
        ai_prompt_version="test-prompts-v1",
        api_prefix="/v1",
    )
    monkeypatch.setattr(main, "settings", production)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["version"] == "1.2.3"
    assert response.json()["commit"] == "c" * 40
    assert "synthetic-key" not in response.text
    assert "z" * 40 not in response.text


def test_validation_errors_do_not_echo_request_data(client: TestClient) -> None:
    private_marker = "private-cv-marker-8492"
    response = client.post(
        "/v1/cv/analyze",
        json={"sections": {"other": [private_marker]}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert private_marker not in response.text


def test_fake_provider_response_has_metadata(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.pipeline import analyze as analyze_pipeline

    class FakeProvider:
        use_mock = False
        provider_name = "groq"
        model_name = "fixture-model"

        async def generate_json(self, **_kwargs) -> dict:
            return {
                "overall_score": 74,
                "dimensions": {
                    "layout_ats": {"score": 75, "issues": [], "fixes": []},
                    "language": {"score": 82, "issues": [], "fixes": []},
                    "keywords": {"score": 68, "missing": [], "suggested_bullets": []},
                    "jd_fit": {"score": 65, "gaps": []},
                },
                "rewrites": [],
                "company_model_feedback": "CV có kinh nghiệm hỗ trợ lớp học và sửa bài tập.",
                "confidence": 0.8,
            }

    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "mock_llm", False)
    monkeypatch.setattr(analyze_pipeline, "get_llm_service", lambda **_kwargs: FakeProvider())
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    body["language"] = "vi"

    response = client.post("/v1/cv/analyze", json=body)

    assert response.status_code == 200
    metadata = response.json()["meta"]
    assert metadata["source"] == "groq"
    assert metadata["provider"] == "groq"
    assert metadata["model"] == "fixture-model"
    assert metadata["schemaVersion"]
    assert metadata["schemaVersion"] == "ai-response-v1"
    assert metadata["promptVersion"]
    assert isinstance(metadata["latencyMs"], (int, float))
    assert response.headers["X-Request-ID"]


def test_provider_error_is_sanitized(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.pipeline import analyze as analyze_pipeline
    from app.services.errors import LLMUpstreamError

    class FailingFakeProvider:
        use_mock = False
        provider_name = "fake-provider"
        model_name = "fixture-model"

        async def generate_json(self, **_kwargs) -> dict:
            raise LLMUpstreamError(status_code=401, message="secret provider payload")

    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "mock_llm", False)
    monkeypatch.setattr(analyze_pipeline, "get_llm_service", lambda **_kwargs: FailingFakeProvider())
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))

    response = client.post("/v1/cv/analyze", json=body)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "secret provider payload" not in response.text
    assert response.headers["X-Request-ID"]


def test_provider_rate_limit_has_stable_code_and_retry_after(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.pipeline import analyze as analyze_pipeline
    from app.services.errors import LLMQuotaError

    class RateLimitedFakeProvider:
        use_mock = False
        provider_name = "groq"
        model_name = "fixture-model"

        async def generate_json(self, **_kwargs) -> dict:
            raise LLMQuotaError(message="sensitive provider response", retry_after_seconds=9)

    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "mock_llm", False)
    monkeypatch.setattr(analyze_pipeline, "get_llm_service", lambda **_kwargs: RateLimitedFakeProvider())
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))

    response = client.post("/v1/cv/analyze", json=body)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "provider_rate_limited"
    assert response.headers["Retry-After"] == "9"
    assert "sensitive provider response" not in response.text


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("provider_timeout", 504),
        ("malformed_provider_response", 502),
        ("unsupported_schema", 502),
    ],
)
def test_provider_error_taxonomy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    status: int,
) -> None:
    from app.core.config import settings
    from app.pipeline import analyze as analyze_pipeline
    from app.services.errors import LLMUpstreamError

    class FailingFakeProvider:
        use_mock = False
        provider_name = "groq"
        model_name = "fixture-model"

        async def generate_json(self, **_kwargs) -> dict:
            raise LLMUpstreamError(status_code=None, message="sensitive fake payload", code=code)

    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "mock_llm", False)
    monkeypatch.setattr(analyze_pipeline, "get_llm_service", lambda **_kwargs: FailingFakeProvider())
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))

    response = client.post("/v1/cv/analyze", json=body)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "sensitive fake payload" not in response.text
    assert response.headers["X-Request-ID"]


def test_list_industries(client: TestClient) -> None:
    response = client.get("/v1/industries")

    assert response.status_code == 200
    industry_list = response.json()["industries"]
    industries = {industry["slug"]: industry for industry in industry_list}
    assert [industry["slug"] for industry in industry_list] == [
        "ai_software",
        "computer_science",
        "business_administration",
        "marketing",
        "finance_banking",
        "hospitality_tourism",
        "language",
        "law",
    ]
    assert industries["law"]["display_name"] == "Luật / Law"
    assert {vertical["slug"] for vertical in industries["law"]["verticals"]} == {
        "general_law",
        "economic_law",
    }
    assert [vertical["slug"] for vertical in industries["business_administration"]["verticals"][:5]] == [
        "general_business",
        "international_business",
        "ecommerce",
        "customer_experience",
        "business_analytics",
    ]
    assert [vertical["slug"] for vertical in industries["language"]["verticals"]] == [
        "english_language",
        "chinese_language",
        "japanese_language",
        "korean_language",
        "translation_interpretation",
        "language_teaching",
    ]
    assert "cybersecurity" in {
        vertical["slug"]
        for vertical in industries["computer_science"]["verticals"]
    }


def test_list_models(client: TestClient) -> None:
    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    model_ids = {model["id"] for model in payload["models"]}
    assert payload["provider"] == "groq"
    assert "qwen/qwen3.8-27b" in model_ids
    assert "qwen/qwen3.6-27b" not in model_ids
    assert "openai/gpt-oss-120b" in model_ids
    assert "qwen/qwen3-32b" not in model_ids
    assert all("llama" not in model_id.lower() for model_id in model_ids)


def test_rejects_unknown_model(client: TestClient) -> None:
    response = client.post(
        "/v1/cv/extract?mode=local&llm_model=unknown-model",
        files={"file": ("cv.pdf", b"not used", "application/pdf")},
    )

    assert response.status_code == 422


def test_auto_language_does_not_treat_vietnamese_name_as_vietnamese_cv() -> None:
    from app.api.v1.cv import _resolve_analysis_language
    from app.pipeline.extract import TargetLanguage
    from app.schemas.cv import CvSections, LanguageMode

    sections = CvSections(
        experience=["Nguyễn Hoàng Duy developed an AI project with Python"],
        education=["Education at FPT University"],
        skills=["Skills include Python and Machine Learning"],
    )

    assert _resolve_analysis_language(TargetLanguage.AUTO, sections) == LanguageMode.EN


def test_analyze_rejects_unknown_industry(client: TestClient) -> None:
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    body["industry_slug"] = "not_a_real_industry"

    response = client.post("/v1/cv/analyze", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_analyze_cv_mock(client: TestClient) -> None:
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    r = client.post("/v1/cv/analyze", json=body)
    assert r.status_code == 200
    data = r.json()
    assert 0 <= data["overall_score"] <= 100
    assert "dimensions" in data
    assert data["meta"]["source"] == "mock"


def test_portfolio_from_image_with_caption(client: TestClient) -> None:
    r = client.post(
        "/v1/portfolio/from-image",
        json={
            "image_url": "https://res.cloudinary.com/demo/image/upload/activity.jpg",
            "industry_slug": "marketing",
            "optional_caption": "Coordinated a student club launch event and handled guest check-in.",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["image_url_received"] == "true"
    assert data["meta"]["needs_user_confirmation"] == "true"
    assert data["confidence"] <= 0.85


def test_portfolio_from_image_without_caption_needs_context(client: TestClient) -> None:
    r = client.post(
        "/v1/portfolio/from-image",
        json={
            "image_url": "https://res.cloudinary.com/demo/image/upload/activity.jpg",
            "industry_slug": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["confidence"] == 0.2
    assert data["suggested_cv_bullet_en"] == ""
    assert data["meta"]["needs_user_confirmation"] == "true"


def test_context_matrix_builder() -> None:
    from app.pipeline.context_matrix import ContextMatrixBuilder
    from app.schemas.cv import AnalyzeCvRequest, CompanyModel, CvSections

    req = AnalyzeCvRequest(
        sections=CvSections(experience=["Test bullet"]),
        industry_slug="language",
        vertical_slug="language_teaching",
        company_model=CompanyModel.CORPORATE,
    )
    ctx = ContextMatrixBuilder().build_for_analyze(req)
    assert "language_teaching" in str(ctx.get("industry_context"))


def test_context_matrix_builder_ai_software() -> None:
    from app.pipeline.context_matrix import ContextMatrixBuilder
    from app.schemas.cv import AnalyzeCvRequest, CompanyModel, CvSections

    req = AnalyzeCvRequest(
        sections=CvSections(projects=["Face recognition attendance system using Python and OpenCV"]),
        industry_slug="ai_software",
        vertical_slug="computer_vision",
        company_model=CompanyModel.CORPORATE,
    )
    ctx = ContextMatrixBuilder().build_for_analyze(req)
    industry_context = str(ctx.get("industry_context"))
    assert "computer_vision" in industry_context
    assert "OpenCV" in industry_context
    assert "model evaluation" in industry_context
    assert "cybersecurity" not in industry_context
    assert "SOC" not in industry_context


@pytest.mark.parametrize(
    ("industry_slug", "vertical_slug", "expected_keyword"),
    [
        ("law", "economic_law", "Commercial Arbitration"),
        ("finance_banking", "fintech", "eKYC"),
        ("business_administration", "logistics_supply_chain", "Bill of Lading"),
        ("computer_science", "cybersecurity", "Vulnerability Assessment"),
        ("ai_software", "machine_learning", "model evaluation"),
    ],
)
def test_context_matrix_builder_new_industries(
    industry_slug: str,
    vertical_slug: str,
    expected_keyword: str,
) -> None:
    from app.pipeline.context_matrix import ContextMatrixBuilder
    from app.schemas.cv import AnalyzeCvRequest, CompanyModel, CvSections

    req = AnalyzeCvRequest(
        sections=CvSections(experience=["Relevant experience"]),
        industry_slug=industry_slug,
        vertical_slug=vertical_slug,
        company_model=CompanyModel.CORPORATE,
    )
    ctx = ContextMatrixBuilder().build_for_analyze(req)
    industry_context = ctx["industry_context"]

    assert industry_context["slug"] == industry_slug
    assert expected_keyword in industry_context["active_vertical"]["keywords"]
    assert "verticals" not in industry_context
