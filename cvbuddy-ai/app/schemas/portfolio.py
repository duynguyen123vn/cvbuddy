from pydantic import BaseModel, Field

from app.schemas.cv import UserTier


class PortfolioSuggestRequest(BaseModel):
    """Activity description from user; image bytes are not sent to the text LLM."""

    activity_text: str = Field(..., min_length=10, max_length=4000)
    industry_slug: str
    vertical_slug: str | None = None
    optional_caption: str | None = None
    tier: UserTier = UserTier.FREE


class PortfolioFromImageRequest(BaseModel):
    """Image URL contract for Locket-style portfolio suggestions.

    The web tier uploads the image to Cloudinary and sends a URL here. Until a
    vision model is enabled, caption/context is required for reliable output.
    """

    image_url: str = Field(..., min_length=8, max_length=2000)
    industry_slug: str
    vertical_slug: str | None = None
    optional_caption: str | None = Field(None, max_length=4000)
    tier: UserTier = UserTier.FREE


class PortfolioSuggestResponse(BaseModel):
    activity_summary_vi: str
    activity_summary_en: str
    suggested_cv_bullet_vi: str
    suggested_cv_bullet_en: str
    action_verbs: list[str] = Field(default_factory=list)
    industry_keywords: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    meta: dict[str, str] = Field(default_factory=dict)
