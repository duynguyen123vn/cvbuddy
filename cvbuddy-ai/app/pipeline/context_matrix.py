"""Build layered context from versioned prompt assets."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from app.schemas.cv import AnalyzeCvRequest, CompanyModel

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


class IndustryContextError(ValueError):
    pass


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ContextMatrixBuilder:
    def __init__(self, prompts_root: Path | None = None) -> None:
        self.root = prompts_root or PROMPTS_ROOT

    def build_for_analyze(self, request: AnalyzeCvRequest) -> dict[str, Any]:
        base_system = _read_text(self.root / "base" / "system.md")
        company_file = (
            "corporate.md"
            if request.company_model == CompanyModel.CORPORATE
            else "startup_agency.md"
        )
        company_rubric = _read_text(self.root / "company_models" / company_file)

        industry = self.resolve_industry(request.industry_slug, request.vertical_slug)

        return {
            "system_instruction": base_system,
            "company_model_rubric": company_rubric,
            "industry_context": industry,
            "company_model": request.company_model.value,
            "industry_slug": request.industry_slug,
            "vertical_slug": request.vertical_slug,
            "language": request.language.value,
            "tier": request.tier.value,
            "jd_extract": request.jd_extract.model_dump() if request.jd_extract else None,
            "local_metrics": (
                request.local_metrics.model_dump() if request.local_metrics else None
            ),
            "cv_sections": request.sections.model_dump(),
        }

    def load_industry(self, industry_slug: str) -> dict[str, Any]:
        return _load_yaml(self.root / "industries" / f"{industry_slug}.yaml")

    def resolve_industry(
        self,
        industry_slug: str,
        vertical_slug: str | None,
    ) -> dict[str, Any]:
        industry = self.load_industry(industry_slug)
        if not industry:
            raise IndustryContextError(f"Nhóm ngành không tồn tại: {industry_slug}")

        if not vertical_slug:
            return industry

        verticals = industry.get("verticals") or {}
        if vertical_slug not in verticals:
            raise IndustryContextError(
                f"Chuyên ngành '{vertical_slug}' không thuộc nhóm ngành '{industry_slug}'."
            )
        selected_context = {
            key: value
            for key, value in industry.items()
            if key != "verticals"
        }
        return {
            **selected_context,
            "active_vertical_slug": vertical_slug,
            "active_vertical": verticals[vertical_slug],
        }

    def validate_industry_match(self, request: AnalyzeCvRequest) -> None:
        if not request.strict_industry_match:
            return

        industry = self.resolve_industry(request.industry_slug, request.vertical_slug)
        vertical = industry.get("active_vertical") or {}
        keywords = vertical.get("keywords") or industry.get("core_keywords") or []
        source = _normalize_match_text(
            " ".join(
                item
                for values in request.sections.model_dump().values()
                for item in values
            )
        )
        matched = [
            keyword
            for keyword in keywords
            if _keyword_matches_source(str(keyword), source)
        ]
        if matched:
            return

        vertical_name = vertical.get("display_name") or request.vertical_slug
        industry_name = industry.get("display_name") or request.industry_slug
        selected = " / ".join(filter(None, (industry_name, vertical_name)))
        raise IndustryContextError(
            f"Nội dung CV không khớp chuyên ngành đã chọn: {selected}. "
            "Hãy chọn lại chuyên ngành hoặc tắt kiểm tra nghiêm ngặt cho hồ sơ chuyển ngành."
        )

    def list_industries(self) -> list[dict[str, Any]]:
        industries: list[dict[str, Any]] = []
        for path in sorted((self.root / "industries").glob("*.yaml")):
            industry = _load_yaml(path)
            slug = industry.get("slug") or path.stem
            verticals = industry.get("verticals") or {}
            industries.append(
                {
                    "slug": slug,
                    "display_name": industry.get("display_name") or slug,
                    "verticals": [
                        {
                            "slug": vertical_slug,
                            "display_name": vertical.get("display_name") or vertical_slug,
                        }
                        for vertical_slug, vertical in verticals.items()
                    ],
                }
            )
        return industries

    def to_prompt_payload(self, context: dict[str, Any]) -> str:
        """Create a stable JSON payload for the configured LLM."""
        return json.dumps(context, ensure_ascii=False, indent=2)


def _normalize_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9+#.]+", " ", ascii_text).strip()


def _keyword_matches_source(keyword: str, normalized_source: str) -> bool:
    normalized_keyword = _normalize_match_text(keyword)
    if not normalized_keyword:
        return False
    if len(normalized_keyword) <= 3:
        return bool(re.search(rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)", normalized_source))
    return normalized_keyword in normalized_source
