"""로드맵 수정 API."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.modify import ModifyRequest, ModifyResponse
from app.services.modify_service import run_modify_pipeline

router = APIRouter(prefix="/api/v1", tags=["modify"])
logger = get_logger(__name__)


@router.post(
    "/modify",
    response_model=ModifyResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_secret)],
)
async def modify_roadmap(request: ModifyRequest) -> ModifyResponse:
    """로드맵 수정 요청을 처리하고 결과를 반환한다."""
    try:
        return await run_modify_pipeline(request)
    except Exception as exc:
        logger.error("로드맵 수정 처리 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로드맵 수정 처리에 실패했습니다.",
        ) from exc
