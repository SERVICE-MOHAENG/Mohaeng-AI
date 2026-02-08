"""로드맵 생성 작업 처리 서비스."""

from __future__ import annotations

import asyncio

import requests

from app.core.config import get_settings
from app.core.logger import get_logger
from app.graph.roadmap import compiled_roadmap_graph
from app.schemas.course import CourseRequest, CourseResponse
from app.schemas.generate import CallbackError, GenerateCallbackFailure, GenerateCallbackSuccess
from app.services.google_places_service import GooglePlacesService

logger = get_logger(__name__)


async def run_roadmap_pipeline(request: CourseRequest) -> CourseResponse:
    """로드맵 그래프를 실행하고 결과를 반환합니다."""
    initial_state = {"course_request": request.model_dump(mode="json")}
    places_service = GooglePlacesService.from_settings()
    result = await compiled_roadmap_graph.ainvoke(
        initial_state,
        config={"configurable": {"places_service": places_service}},
    )

    if error := result.get("error"):
        raise RuntimeError(error)

    final = result.get("final_roadmap")
    if not final:
        raise RuntimeError("final_roadmap 결과가 없습니다.")

    return CourseResponse.model_validate(final)


def _build_callback_url(base_url: str, job_id: str) -> str:
    """콜백 URL을 구성합니다."""
    return f"{base_url.rstrip('/')}/itineraries/{job_id}/result"


async def _post_callback(callback_url: str, payload: dict, timeout_seconds: int, service_secret: str) -> None:
    """콜백 URL로 결과를 전송합니다."""

    def _send() -> None:
        response = requests.post(
            callback_url,
            json=payload,
            headers={"x-service-secret": service_secret},
            timeout=timeout_seconds,
        )
        response.raise_for_status()

    try:
        await asyncio.to_thread(_send)
    except Exception as exc:
        logger.error("콜백 전송 실패: %s", exc)


async def process_generate_request(job_id: str, callback_url: str, payload: CourseRequest) -> None:
    """로드맵 생성 후 콜백을 전송합니다."""
    settings = get_settings()

    try:
        roadmap = await asyncio.wait_for(
            run_roadmap_pipeline(payload),
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        callback = GenerateCallbackSuccess(data=roadmap)
        payload_data = callback.model_dump(mode="json")
    except asyncio.TimeoutError:
        callback = GenerateCallbackFailure(
            error=CallbackError(code="LLM_TIMEOUT", message="LLM 생성 시간이 초과되었습니다."),
        )
        payload_data = callback.model_dump(mode="json")
    except Exception as exc:
        callback = GenerateCallbackFailure(
            error=CallbackError(code="PIPELINE_ERROR", message=str(exc)),
        )
        payload_data = callback.model_dump(mode="json")

    callback_endpoint = _build_callback_url(callback_url, job_id)
    await _post_callback(
        callback_url=callback_endpoint,
        payload=payload_data,
        timeout_seconds=settings.CALLBACK_TIMEOUT_SECONDS,
        service_secret=settings.SERVICE_SECRET,
    )
