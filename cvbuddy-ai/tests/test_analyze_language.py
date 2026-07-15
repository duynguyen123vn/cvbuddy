import pytest

from app.pipeline.analyze import (
    _feedback_is_generic,
    _feedback_language_mismatch,
    run_cv_analyze,
)
from app.schemas.cv import AnalyzeCvRequest, CvSections, LanguageMode


def _raw_response(feedback: str) -> dict:
    return {
        "overall_score": 70,
        "dimensions": {
            "layout_ats": {"score": 70, "issues": [feedback], "fixes": [feedback]},
            "language": {"score": 70, "issues": [], "fixes": []},
            "keywords": {"score": 70, "missing": [], "suggested_bullets": []},
            "jd_fit": {"score": 65, "gaps": []},
        },
        "rewrites": [],
        "company_model_feedback": feedback,
        "confidence": 0.8,
    }


def test_detects_english_feedback_when_vietnamese_expected() -> None:
    raw = _raw_response(
        "The experience section should include clear job descriptions and skills."
    )

    assert _feedback_language_mismatch(raw, "vi") is True
    assert _feedback_language_mismatch(raw, "en") is False


def test_detects_mixed_response_with_vietnamese_summary_but_english_details() -> None:
    raw = _raw_response("CV cần tập trung vào kỹ năng kỹ thuật cụ thể.")
    raw["dimensions"]["layout_ats"] = {
        "score": 60,
        "issues": [
            "Duplicate content exists between experience and projects sections.",
            "The summary contains personal details that reduce ATS readability.",
        ],
        "fixes": [
            "Merge duplicate project entries.",
            "Remove unrelated personal details from the summary.",
        ],
    }

    assert _feedback_language_mismatch(raw, "vi") is True


def test_detects_generic_feedback_without_evidence() -> None:
    raw = _raw_response("Thiếu tính cụ thể. Cần sử dụng từ ngữ chuyên nghiệp.")

    assert _feedback_is_generic(raw) is True


class _RetryingService:
    use_mock = False
    provider_name = "groq"
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, **_kwargs) -> dict:
        self.calls += 1
        if self.calls == 1:
            return _raw_response(
                "The experience section should include clear job descriptions and skills."
            )
        return _raw_response(
            "Phần kinh nghiệm cần trình bày kỹ năng và mô tả công việc rõ ràng."
        )


@pytest.mark.asyncio
async def test_analyze_retries_once_when_feedback_language_is_wrong() -> None:
    service = _RetryingService()
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["Phát triển dự án AI"]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    result = await run_cv_analyze(request, llm_service=service)

    assert service.calls == 2
    assert "Phần kinh nghiệm" in result.company_model_feedback
    assert result.meta["language"] == "vi"

