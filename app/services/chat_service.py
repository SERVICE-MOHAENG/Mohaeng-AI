"""로드맵 대화 작업 처리 서비스."""

from __future__ import annotations

import asyncio

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
    }

    try:
        result = await compiled_chat_graph.ainvoke(initial_state)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("대화 그래프 실행 중 예외 발생")
        return ChatResponse(
            status=ChatStatus.REJECTED,
            message="요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )

    status = result.get("status", ChatStatus.SUCCESS)
    message = result.get("message") or result.get("change_summary") or result.get("clarification_question") or ""

    if error := result.get("error"):
        logger.error("대화 파이프라인 에러: %s", error)
        return ChatResponse(
            status=ChatStatus.REJECTED,
            message=result.get("message") or "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return ChatResponse(
        status=status,
        modified_itinerary=result.get("modified_itinerary"),
        message=message,
        diff_keys=result.get("diff_keys", []),
    )
