from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message")
    code: str | None = Field(None, description="Machine-readable error code")
