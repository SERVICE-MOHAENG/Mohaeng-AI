"""로드맵 생성 트리거 API."""

import asyncio

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.generate import GenerateAckResponse, GenerateRequest
from app.services.generate_service import process_generate_request

router = APIRouter(prefix="/api/v1", tags=["generate"])
logger = get_logger(__name__)


@router.post(
    "/generate",
    response_model=GenerateAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_secret)],
)
async def generate_roadmap(request: GenerateRequest) -> GenerateAckResponse:
    """로드맵 생성 작업을 수락하고 비동기로 처리한다."""
    asyncio.create_task(
        process_generate_request(
            job_id=request.job_id,
            callback_url=str(request.callback_url),
            payload=request.payload,
        )
    )
    logger.info("Generate request accepted: %s", request.job_id)
    return GenerateAckResponse(job_id=request.job_id)
