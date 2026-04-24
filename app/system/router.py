from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


@router.get("/health", response_model=HealthResponse, operation_id="getHealth")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
