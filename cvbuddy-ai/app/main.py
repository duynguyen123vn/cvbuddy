from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_handlers import install_error_handlers
from app.core.http_middleware import ProductionGateMiddleware
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_production_config()
    setup_logging()
    yield


app = FastAPI(
    title="CVBuddy AI",
    description="Local document extraction → Groq Qwen → structured CV analysis",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "X-Request-ID"],
)
app.add_middleware(ProductionGateMiddleware, config=settings)

app.include_router(api_router, prefix=settings.api_prefix)
install_error_handlers(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cvbuddy-ai", "env": settings.app_env}
