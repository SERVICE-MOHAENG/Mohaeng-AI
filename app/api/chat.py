"""로드맵 대화 API."""

import asyncio

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.chat import ChatAckResponse, ChatRequest
from app.services.chat_service import process_chat_request

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = get_logger(__name__)
active_tasks: set[asyncio.Task] = set()


def _on_chat_task_done(task: asyncio.Task) -> None:
    active_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("Chat task cancelled")
        return

    if exc is not None:
        logger.exception("Chat task failed", exc_info=exc)


CHAT_ACK_EXAMPLES = {
    "accepted": {
        "summary": "요청 수락",
        "description": "비동기 처리 요청이 정상적으로 접수된 경우",
        "value": {"status": "ACCEPTED", "job_id": "modify-job-12345"},
    }
}


@router.post(
    "/chat",
    response_model=ChatAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_secret)],
    responses={
        202: {
            "description": "대화 요청 수락",
            "content": {
                "application/json": {
                    "examples": CHAT_ACK_EXAMPLES,
                }
            },
        }
    },
)
async def chat_roadmap(request: ChatRequest) -> ChatAckResponse:
    """로드맵 대화 요청을 접수하고 비동기 처리한다."""
    task = asyncio.create_task(process_chat_request(request))
    active_tasks.add(task)
    task.add_done_callback(_on_chat_task_done)
    logger.info("Chat request accepted: %s", request.job_id)
    return ChatAckResponse(job_id=request.job_id)
