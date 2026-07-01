from fastapi import APIRouter

from app.api.v1 import cv, industries, models, portfolio, translate

api_router = APIRouter()
api_router.include_router(cv.router, tags=["cv"])
api_router.include_router(industries.router, tags=["industries"])
api_router.include_router(models.router, tags=["models"])
api_router.include_router(translate.router, tags=["translate"])
api_router.include_router(portfolio.router, tags=["portfolio"])
