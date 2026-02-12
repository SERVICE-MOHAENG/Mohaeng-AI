"""로드맵 대화 작업 처리 서비스."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.chat import compiled_chat_graph
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.enums import ChatStatus
from app.services.callback_delivery import post_callback_with_retry

logger = get_logger(__name__)


async def run_chat_pipeline(request: ChatRequest) -> ChatResponse:
    """로드맵 대화 그래프를 실행하고 결과를 반환합니다."""
    current_itinerary = request.current_itinerary
    if isinstance(current_itinerary, BaseModel):
        current_itinerary = current_itinerary.model_dump(mode="json")

    initial_state = {
        "current_itinerary": current_itinerary,
        "user_query": request.user_query,
        "session_history": [msg.model_dump() for msg in request.session_history],
    }

    try:
        result = await compiled_chat_graph.ainvoke(initial_state)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("대화 그래프 실행 중 예외 발생")
        raise

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


def _serialize_itinerary(itinerary: Any) -> dict | None:
    if itinerary is None:
        return None
    if isinstance(itinerary, BaseModel):
        return itinerary.model_dump(mode="json")
    if isinstance(itinerary, dict):
        return itinerary
    return None


def _build_callback_payload(result: ChatResponse) -> dict:
    status_value = result.status.value if isinstance(result.status, ChatStatus) else str(result.status)
    payload = {
        "status": status_value,
        "message": result.message or "",
        "diff_keys": result.diff_keys or [],
        "modified_itinerary": None,
    }

    if status_value == ChatStatus.SUCCESS.value:
        payload["modified_itinerary"] = _serialize_itinerary(result.modified_itinerary)

    return payload


def _build_chat_callback_url(base_url: str, job_id: str) -> str:
    """NestJS 콜백 엔드포인트를 구성합니다."""
    return f"{base_url.rstrip('/')}/itineraries/{job_id}/chat-result"


async def _post_callback(
    callback_url: str,
    payload: dict,
    timeout_seconds: int,
    service_secret: str,
    job_id: str,
) -> None:
    """콜백 URL로 결과를 전송합니다."""
    headers = {"x-service-secret": service_secret} if service_secret else {}
    await post_callback_with_retry(
        callback_url=callback_url,
        payload=payload,
        headers=headers,
        timeout_seconds=timeout_seconds,
        context={"job_id": job_id, "callback_type": "chat"},
    )


async def process_chat_request(request: ChatRequest) -> None:
    """대화 요청을 처리하고 콜백으로 결과를 전달합니다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)

    try:
        result = await asyncio.wait_for(
            run_chat_pipeline(request),
            timeout=timeout_policy.llm_timeout_seconds,
        )
        payload = _build_callback_payload(result)
    except asyncio.TimeoutError:
        payload = {
            "status": ChatStatus.FAILED.value,
            "error": {"code": "LLM_TIMEOUT", "message": "LLM 응답 시간이 초과되었습니다."},
        }
    except Exception:
        logger.exception("대화 파이프라인 처리 중 예외 발생")
        payload = {
            "status": ChatStatus.FAILED.value,
            "error": {"code": "PIPELINE_ERROR", "message": "대화 처리 중 내부 오류가 발생했습니다."},
        }

    callback_endpoint = _build_chat_callback_url(str(request.callback_url), request.job_id)
    await _post_callback(
        callback_url=callback_endpoint,
        payload=payload,
        timeout_seconds=timeout_policy.callback_timeout_seconds,
        service_secret=settings.SERVICE_SECRET,
        job_id=request.job_id,
    )
