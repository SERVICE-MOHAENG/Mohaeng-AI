"""설문 기반 추천 트리거 API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.recommend import RecommendAckResponse, RecommendRequest
from app.services.recommend_service import process_recommend_request

router = APIRouter(prefix="/api/v1", tags=["recommend"])
logger = get_logger(__name__)
active_tasks: set[asyncio.Task] = set()


RECOMMEND_ACK_EXAMPLES = {
    "accepted": {
        "summary": "요청 접수",
        "description": "추천 작업이 비동기 처리 대상으로 정상 접수됨",
        "value": {"status": "ACCEPTED", "job_id": "recommend-job-12345"},
    }
}


def _on_recommend_task_done(task: asyncio.Task) -> None:
    active_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("Recommend task cancelled")
        return

    if exc is not None:
        logger.exception("Recommend task failed", exc_info=exc)


@router.post(
    "/recommend",
    response_model=RecommendAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_secret)],
    responses={
        202: {
            "description": "Recommendation request accepted",
            "content": {"application/json": {"examples": RECOMMEND_ACK_EXAMPLES}},
        },
    },
)
async def recommend(request: RecommendRequest) -> RecommendAckResponse:
    """추천 요청을 접수하고 비동기 작업으로 처리한다."""
    task = asyncio.create_task(process_recommend_request(request))
    active_tasks.add(task)
    task.add_done_callback(_on_recommend_task_done)
    logger.info("Recommend request accepted: %s", request.job_id)
    return RecommendAckResponse(job_id=request.job_id)
