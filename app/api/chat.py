"""로드맵 대화 API."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import run_chat_pipeline

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = get_logger(__name__)


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_secret)],
)
async def chat_roadmap(request: ChatRequest) -> ChatResponse:
    """로드맵 대화 요청을 처리하고 결과를 반환한다."""
    try:
        return await run_chat_pipeline(request)
    except Exception as exc:
        logger.error("로드맵 대화 처리 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로드맵 대화 처리에 실패했습니다.",
        ) from exc
