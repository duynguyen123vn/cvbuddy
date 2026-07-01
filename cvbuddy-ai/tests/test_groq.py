import pytest

from app.services.groq import _parse_json_loose


def test_parse_json_loose_ignores_qwen_thinking() -> None:
    response = """<think>
The requested schema resembles {"score": "number"}.
</think>
{"overall_score": 75, "confidence": 0.8}
"""

    assert _parse_json_loose(response) == {
        "overall_score": 75,
        "confidence": 0.8,
    }


def test_parse_json_loose_rejects_missing_json() -> None:
    with pytest.raises(ValueError):
        _parse_json_loose("No JSON was returned")
