"""로드맵 생성 트리거 API."""

import asyncio

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.generate import GenerateAckResponse, GenerateRequest
from app.services.generate_service import process_generate_request

router = APIRouter(prefix="/api/v1", tags=["generate"])
logger = get_logger(__name__)
active_tasks: set[asyncio.Task] = set()


def _on_generate_task_done(task: asyncio.Task) -> None:
    active_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("Generate task cancelled")
        return

    if exc is not None:
        logger.exception("Generate task failed", exc_info=exc)


@router.post(
    "/generate",
    response_model=GenerateAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_secret)],
)
async def generate_roadmap(request: GenerateRequest) -> GenerateAckResponse:
    """로드맵 생성 작업을 수락하고 비동기로 처리한다."""
    task = asyncio.create_task(
        process_generate_request(
            job_id=request.job_id,
            callback_url=str(request.callback_url),
            payload=request.payload,
        )
    )
    active_tasks.add(task)
    task.add_done_callback(_on_generate_task_done)
    logger.info("Generate request accepted: %s", request.job_id)
    return GenerateAckResponse(job_id=request.job_id)
