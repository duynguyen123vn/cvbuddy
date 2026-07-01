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


def test_list_industries(client: TestClient) -> None:
    response = client.get("/v1/industries")

    assert response.status_code == 200
    industries = {
        industry["slug"]: industry for industry in response.json()["industries"]
    }
    assert industries["law"]["display_name"] == "Luật / Law"
    assert {vertical["slug"] for vertical in industries["law"]["verticals"]} == {
        "general_law",
        "economic_law",
    }
    assert "cybersecurity" in {
        vertical["slug"]
        for vertical in industries["computer_science"]["verticals"]
    }


def test_list_models(client: TestClient) -> None:
    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    model_ids = {model["id"] for model in payload["models"]}
    assert payload["provider"] in {"groq", "ollama"}
    if payload["provider"] == "ollama":
        assert "qwen3:8b" in model_ids
    else:
        assert "qwen/qwen3.6-27b" in model_ids
        assert "meta-llama/llama-4-scout-17b-16e-instruct" in model_ids


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
    assert "Nhóm ngành không tồn tại" in response.json()["detail"]


def test_analyze_cv_mock(client: TestClient) -> None:
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    r = client.post("/v1/cv/analyze", json=body)
    assert r.status_code == 200
    data = r.json()
    assert 0 <= data["overall_score"] <= 100
    assert "dimensions" in data
    assert data["meta"]["source"] == "mock"


def test_ai_contract_alias_for_analyze_cv(client: TestClient) -> None:
    body = json.loads((FIXTURES / "analyze_request_sample.json").read_text(encoding="utf-8"))
    r = client.post("/ai/cv/analyze", json=body)
    assert r.status_code == 200
    assert r.json()["meta"]["source"] == "mock"


def test_portfolio_from_image_with_caption(client: TestClient) -> None:
    r = client.post(
        "/ai/portfolio/from-image",
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
        "/ai/portfolio/from-image",
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
        vertical_slug="english_center",
        company_model=CompanyModel.CORPORATE,
    )
    ctx = ContextMatrixBuilder().build_for_analyze(req)
    assert "english_center" in str(ctx.get("industry_context"))


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
        ("business_administration", "fintech", "eKYC"),
        ("business_administration", "logistics_supply_chain", "Bill of Lading"),
        ("computer_science", "cybersecurity", "Vulnerability Assessment"),
        ("computer_science", "ai_data_science", "Predictive Modeling"),
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
