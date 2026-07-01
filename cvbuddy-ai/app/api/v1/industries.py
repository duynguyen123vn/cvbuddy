from fastapi import APIRouter

from app.pipeline.context_matrix import ContextMatrixBuilder

router = APIRouter(prefix="/industries")


@router.get("")
def list_industries() -> dict[str, list[dict]]:
    """Return industry and vertical slugs for web form selectors."""
    return {"industries": ContextMatrixBuilder().list_industries()}
