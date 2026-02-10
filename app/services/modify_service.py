"""로드맵 수정 작업 처리 서비스."""

from __future__ import annotations

from app.core.logger import get_logger
from app.graph.modify import compiled_modify_graph
from app.schemas.enums import ModifyStatus
from app.schemas.modify import ModifyRequest, ModifyResponse

logger = get_logger(__name__)


async def run_modify_pipeline(request: ModifyRequest) -> ModifyResponse:
    """로드맵 수정 그래프를 실행하고 결과를 반환합니다."""
    initial_state = {
        "current_itinerary": request.current_itinerary.model_dump(mode="json"),
        "user_query": request.user_query,
        "session_history": [msg.model_dump() for msg in request.session_history],
        "metadata": request.metadata.model_dump() if request.metadata else {},
    }

    result = await compiled_modify_graph.ainvoke(initial_state)

    status = result.get("status", ModifyStatus.SUCCESS)
    change_summary = result.get("change_summary", "")

    if error := result.get("error"):
        logger.error("수정 파이프라인 에러: %s", error)
        return ModifyResponse(
            status=ModifyStatus.REJECTED,
            change_summary=error,
        )

    return ModifyResponse(
        status=status,
        modified_itinerary=result.get("modified_itinerary"),
        change_summary=change_summary,
        diff_keys=result.get("diff_keys", []),
        warnings=result.get("warnings", []),
        suggested_keyword=result.get("suggested_keyword"),
    )
