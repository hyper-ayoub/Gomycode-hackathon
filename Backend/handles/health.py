from fastapi import APIRouter
from pydantic import BaseModel

from core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    openai_configured: bool
    llmwhisperer_configured: bool


@router.get("/health", response_model=HealthResponse, summary="Liveness/readiness check")
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="darijadoc-backend",
        environment=settings.APP_ENV,
        openai_configured=settings.openai_configured,
        llmwhisperer_configured=settings.llmwhisperer_configured,
    )
