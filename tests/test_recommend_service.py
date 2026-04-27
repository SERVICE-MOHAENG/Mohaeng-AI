"""추천 서비스 예외 메시지 노출 정책 테스트."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.schemas.recommend import RecommendRequest


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_process_recommend_request_hides_internal_error_by_default(monkeypatch) -> None:
    _set_required_env(monkeypatch, EXPOSE_INTERNAL_ERRORS="false")
    import app.services.recommend_service as recommend_service

    captured_payload: dict = {}
    captured_events: list[dict] = []

    async def _fake_run_pipeline(_request):
        raise RuntimeError("sensitive: internal detail")

    async def _fake_post_callback(callback_url, payload, timeout_seconds, service_secret, job_id):
        captured_payload.update(payload)

    async def _fake_notify(**kwargs):
        captured_events.append(kwargs)

    monkeypatch.setattr(recommend_service, "run_recommendation_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(recommend_service, "_post_callback", _fake_post_callback)
    monkeypatch.setattr(recommend_service, "_notify_pipeline_event_best_effort", _fake_notify)

    request = RecommendRequest(job_id="job-1", callback_url="https://example.com/internal")
    asyncio.run(recommend_service.process_recommend_request(request))

    assert captured_payload["status"] == "FAILED"
    assert captured_payload["error"]["code"] == "PIPELINE_ERROR"
    assert captured_payload["error"]["message"] == "추천 처리 중 내부 오류가 발생했습니다."
    assert [event["event_type"] for event in captured_events] == [
        "recommend_request_received",
        "recommend_completed",
    ]
    assert captured_events[0]["title"] == "여행지 추천 접수"
    assert any(field["name"] == "설문 요청" for field in captured_events[0]["extra_fields"])
    assert any(field["name"] == "오류 상세" for field in captured_events[1]["extra_fields"])
    assert captured_events[1]["status"] == "FAILED"


def test_process_recommend_request_exposes_internal_error_when_enabled(monkeypatch) -> None:
    _set_required_env(monkeypatch, EXPOSE_INTERNAL_ERRORS="true")
    import app.services.recommend_service as recommend_service

    captured_payload: dict = {}
    captured_events: list[dict] = []

    async def _fake_run_pipeline(_request):
        raise RuntimeError("sensitive: internal detail")

    async def _fake_post_callback(callback_url, payload, timeout_seconds, service_secret, job_id):
        captured_payload.update(payload)

    async def _fake_notify(**kwargs):
        captured_events.append(kwargs)

    monkeypatch.setattr(recommend_service, "run_recommendation_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(recommend_service, "_post_callback", _fake_post_callback)
    monkeypatch.setattr(recommend_service, "_notify_pipeline_event_best_effort", _fake_notify)

    request = RecommendRequest(job_id="job-2", callback_url="https://example.com/internal")
    asyncio.run(recommend_service.process_recommend_request(request))

    assert captured_payload["status"] == "FAILED"
    assert captured_payload["error"]["code"] == "PIPELINE_ERROR"
    assert captured_payload["error"]["message"] == "sensitive: internal detail"
    assert [event["event_type"] for event in captured_events] == [
        "recommend_request_received",
        "recommend_completed",
    ]
    assert captured_events[0]["title"] == "여행지 추천 접수"
    assert captured_events[1]["error"] == "sensitive: internal detail"
