from pathlib import Path

from app.pipeline.analyze import ANALYZE_RESPONSE_SCHEMA_HINT


ROOT = Path(__file__).resolve().parents[1]


def test_analyze_prompt_blocks_invented_metrics_in_rewrites() -> None:
    system_prompt = (ROOT / "prompts" / "base" / "system.md").read_text(encoding="utf-8")
    combined = f"{system_prompt}\n{ANALYZE_RESPONSE_SCHEMA_HINT}"

    assert "Never place invented numbers" in combined
    assert "Never insert made-up metrics" in combined
    assert "keywords.suggested_bullets" in combined
    assert "deployed, launched, managed" in combined
    assert "[add measured accuracy]" in combined
    assert "needs_user_fact true" in combined


def test_analyze_prompt_handles_missing_jd_context() -> None:
    assert "When jd_extract is null" in ANALYZE_RESPONSE_SCHEMA_HINT
    assert "neutral 60-70 range" in ANALYZE_RESPONSE_SCHEMA_HINT
    assert "do not treat missing JD as poor fit" in ANALYZE_RESPONSE_SCHEMA_HINT


def test_extract_prompt_handles_bilingual_cv_versions() -> None:
    extract_prompt = (ROOT / "prompts" / "base" / "extract_sections.md").read_text(encoding="utf-8")

    assert "target_language" in extract_prompt
    assert "ignore the Vietnamese duplicate" in extract_prompt
    assert "ignore the English duplicate" in extract_prompt
    assert "do not merge versions" in extract_prompt
