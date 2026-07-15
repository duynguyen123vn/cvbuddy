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

INDUSTRY_DISPLAY_ORDER = {
    "ai_software": 10,
    "computer_science": 20,
    "business_administration": 30,
    "marketing": 40,
    "finance_banking": 50,
    "hospitality_tourism": 60,
    "language": 70,
    "law": 80,
}

VERTICAL_DISPLAY_ORDER = {
    "ai_software": {
        "machine_learning": 10,
        "data_science": 20,
        "computer_vision": 30,
        "nlp": 40,
        "backend_ai": 50,
    },
    "computer_science": {
        "software_engineering": 10,
        "web_development": 20,
        "mobile_development": 30,
        "data_engineering": 40,
        "cybersecurity": 50,
        "information_systems": 60,
        "cloud_devops": 70,
    },
    "business_administration": {
        "general_business": 10,
        "international_business": 20,
        "ecommerce": 30,
        "customer_experience": 40,
        "business_analytics": 50,
        "logistics_supply_chain": 60,
        "procurement": 70,
        "event_management": 80,
    },
    "marketing": {
        "digital_marketing": 10,
        "content_marketing": 20,
        "social_media": 30,
        "brand_management": 40,
        "performance_marketing": 50,
        "public_relations": 60,
        "market_research": 70,
    },
    "finance_banking": {
        "banking_finance": 10,
        "corporate_finance": 20,
        "fintech": 30,
        "smart_finance": 40,
    },
    "hospitality_tourism": {
        "hospitality_management": 10,
        "tourism_travel": 20,
        "restaurant_service": 30,
    },
    "language": {
        "english_language": 10,
        "chinese_language": 20,
        "japanese_language": 30,
        "korean_language": 40,
        "translation_interpretation": 50,
        "language_teaching": 60,
    },
    "law": {
        "general_law": 10,
        "economic_law": 20,
    },
}


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
            vertical_order = VERTICAL_DISPLAY_ORDER.get(slug, {})
            industries.append(
                {
                    "slug": slug,
                    "display_name": industry.get("display_name") or slug,
                    "verticals": [
                        {
                            "slug": vertical_slug,
                            "display_name": vertical.get("display_name") or vertical_slug,
                        }
                        for vertical_slug, vertical in sorted(
                            verticals.items(),
                            key=lambda item: (
                                vertical_order.get(item[0], 10_000),
                                item[1].get("display_name") or item[0],
                            ),
                        )
                    ],
                }
            )
        return sorted(
            industries,
            key=lambda industry: (
                INDUSTRY_DISPLAY_ORDER.get(industry["slug"], 10_000),
                industry["display_name"],
            ),
        )

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
