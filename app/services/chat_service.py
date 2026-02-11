"""로드맵 대화 작업 처리 서비스."""

from __future__ import annotations

from app.core.logger import get_logger
from app.graph.chat import compiled_chat_graph
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.enums import ChatStatus

logger = get_logger(__name__)


async def run_chat_pipeline(request: ChatRequest) -> ChatResponse:
    """로드맵 대화 그래프를 실행하고 결과를 반환합니다."""
    initial_state = {
        "current_itinerary": request.current_itinerary.model_dump(mode="json"),
        "user_query": request.user_query,
        "session_history": [msg.model_dump() for msg in request.session_history],
        "metadata": request.metadata.model_dump() if request.metadata else {},
    }

    result = await compiled_chat_graph.ainvoke(initial_state)

    status = result.get("status", ChatStatus.SUCCESS)
    change_summary = result.get("change_summary", "")

    if error := result.get("error"):
        logger.error("대화 파이프라인 에러: %s", error)
        return ChatResponse(
            status=ChatStatus.REJECTED,
            change_summary=error,
        )

    return ChatResponse(
        status=status,
        modified_itinerary=result.get("modified_itinerary"),
        change_summary=change_summary,
        diff_keys=result.get("diff_keys", []),
        warnings=result.get("warnings", []),
        suggested_keyword=result.get("suggested_keyword"),
        clarification_question=result.get("clarification_question"),
    )
