from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.cv import ProviderMetadata, UserTier


class TranslateMode(StrEnum):
    LITERAL = "literal"
    CV_NATIVE = "cv_native"


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    source_lang: str = "vi"
    target_lang: str = "en"
    mode: TranslateMode = TranslateMode.CV_NATIVE
    tier: UserTier = UserTier.FREE


class TranslateResponse(BaseModel):
    translated: str
    notes: list[str] = Field(default_factory=list, description="Style or grammar hints")
    meta: ProviderMetadata = Field(default_factory=ProviderMetadata)
