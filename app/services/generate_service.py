"""로드맵 생성 작업 처리 서비스."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.job_log_context import append_job_log, collect_job_logs, init_job_log
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.roadmap import compiled_roadmap_graph
from app.schemas.course import CourseRequest, CourseResponse
from app.schemas.generate import CallbackError, GenerateCallbackFailure, GenerateCallbackSuccess
from app.services.callback_delivery import post_callback_with_retry
from app.services.callback_url import build_callback_url
from app.services.google_places_service import get_google_places_service
from app.services.webhook_notification import notify_job_completed, notify_pipeline_event, notify_timeout

logger = get_logger(__name__)


async def _notify_pipeline_event_best_effort(**kwargs) -> None:
    """Discord 웹훅 알림은 실패해도 주 흐름을 막지 않습니다."""
    try:
        await notify_pipeline_event(**kwargs)
    except Exception as exc:
        logger.warning(
            "Generate pipeline webhook failed: event_type=%s stage=%s status=%s error=%s",
            kwargs.get("event_type"),
            kwargs.get("stage"),
            kwargs.get("status"),
            exc,
        )


async def run_roadmap_pipeline(request: CourseRequest) -> CourseResponse:
    """로드맵 그래프를 실행하고 결과를 반환합니다."""
    initial_state = {"course_request": request.model_dump(mode="json")}
    places_service = get_google_places_service()
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


async def _post_callback(
    callback_url: str,
    payload: dict,
    timeout_seconds: int,
    service_secret: str,
    job_id: str,
) -> None:
    """콜백 URL로 결과를 전송합니다."""
    await post_callback_with_retry(
        callback_url=callback_url,
        payload=payload,
        headers={"x-service-secret": service_secret},
        timeout_seconds=timeout_seconds,
        context={"job_id": job_id, "callback_type": "generate"},
    )


async def process_generate_request(job_id: str, callback_url: str, payload: CourseRequest) -> None:
    """로드맵 생성 후 콜백을 전송합니다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)
    init_job_log(job_id)
    append_job_log("job_start", f"type=generate job_id={job_id}")
    await _notify_pipeline_event_best_effort(
        event_type="generate_started",
        severity="info",
        stage="generate",
        status="STARTED",
        title="🚀 Generate Job Started",
        message="로드맵 생성 작업이 시작되었습니다.",
        job_id=job_id,
    )
    status = "SUCCESS"

    try:
        roadmap = await asyncio.wait_for(
            run_roadmap_pipeline(payload),
            timeout=timeout_policy.llm_timeout_seconds,
        )
        callback = GenerateCallbackSuccess(data=roadmap)
        payload_data = callback.model_dump(mode="json")
    except asyncio.TimeoutError:
        status = "TIMEOUT"
        _, logs, elapsed = collect_job_logs()
        logger.warning("Generate timeout: job_id=%s elapsed=%.1fs", job_id, elapsed)
        try:
            await notify_timeout(job_id, "generate", elapsed)
        except Exception as exc:
            logger.warning("Generate timeout webhook failed: job_id=%s error=%s", job_id, exc)
        callback = GenerateCallbackFailure(
            error=CallbackError(code="LLM_TIMEOUT", message="LLM 생성 시간이 초과되었습니다."),
        )
        payload_data = callback.model_dump(mode="json")
    except Exception as exc:
        status = "FAILED"
        callback = GenerateCallbackFailure(
            error=CallbackError(code="PIPELINE_ERROR", message=str(exc)),
        )
        payload_data = callback.model_dump(mode="json")

    if status != "TIMEOUT":
        _, logs, elapsed = collect_job_logs()

    try:
        await notify_job_completed(job_id, "generate", elapsed, status, logs)
    except Exception as exc:
        logger.warning("Generate job_completed webhook failed: job_id=%s error=%s", job_id, exc)
    await _notify_pipeline_event_best_effort(
        event_type="generate_completed",
        severity="success" if status == "SUCCESS" else "error",
        stage="generate",
        status=status,
        title="✅ Generate Job Finished",
        message="로드맵 생성 작업이 종료되었습니다.",
        job_id=job_id,
        elapsed_ms=round(elapsed * 1000),
    )

    callback_endpoint = build_callback_url(callback_url, job_id, "itineraries/{job_id}/result")
    await _post_callback(
        callback_url=callback_endpoint,
        payload=payload_data,
        timeout_seconds=timeout_policy.callback_timeout_seconds,
        service_secret=settings.SERVICE_SECRET,
        job_id=job_id,
    )
