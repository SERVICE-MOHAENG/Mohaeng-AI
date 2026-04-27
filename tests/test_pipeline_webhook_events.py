"""서비스 파이프라인 웹훅 이벤트 테스트."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.schemas.chat import ChatRequest
from app.schemas.course import CourseRequest


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _chat_request() -> ChatRequest:
    return ChatRequest(
        job_id="chat-job-1",
        callback_url="https://example.com/internal",
        current_itinerary={
            "start_date": "2026-02-11",
            "end_date": "2026-02-11",
            "trip_days": 1,
            "nights": 0,
            "people_count": 2,
            "tags": ["test"],
            "title": "테스트 일정",
            "summary": "테스트 일정입니다.",
            "planning_preference": "PLANNED",
            "itinerary": [],
        },
        companion_type=["FAMILY"],
        travel_themes=["UNIQUE_TRIP"],
        pace_preference="DENSE",
        planning_preference="PLANNED",
        destination_preference="TOURIST_SPOTS",
        activity_preference="ACTIVE",
        priority_preference="EFFICIENCY",
        user_query="1일차 1번째 장소를 바꿔줘",
    )


def _course_request() -> CourseRequest:
    return CourseRequest(
        start_date="2026-02-07",
        end_date="2026-02-07",
        regions=[{"region": "SEOUL", "start_date": "2026-02-07", "end_date": "2026-02-07"}],
        people_count=2,
        companion_type=["FAMILY"],
        travel_themes=["UNIQUE_TRIP"],
        pace_preference="DENSE",
        planning_preference="PLANNED",
        destination_preference="TOURIST_SPOTS",
        activity_preference="ACTIVE",
        priority_preference="EFFICIENCY",
    )


def test_chat_pipeline_emits_started_and_failed_webhooks(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    import app.services.chat_service as chat_service

    captured_events: list[dict] = []
    captured_payload: dict = {}

    async def _fake_run_pipeline(_request):
        raise RuntimeError("chat boom")

    async def _fake_notify(**kwargs):
        captured_events.append(kwargs)

    async def _fake_post_callback(callback_url, payload, timeout_seconds, service_secret, job_id):
        captured_payload.update(payload)

    monkeypatch.setattr(chat_service, "run_chat_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(chat_service, "_notify_pipeline_event_best_effort", _fake_notify)
    monkeypatch.setattr(chat_service, "_post_callback", _fake_post_callback)

    asyncio.run(chat_service.process_chat_request(_chat_request()))

    assert captured_payload["status"] == "FAILED"
    assert [event["event_type"] for event in captured_events] == ["chat_started", "chat_completed"]
    assert captured_events[1]["status"] == "FAILED"


def test_generate_pipeline_emits_started_and_failed_webhooks(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    import app.services.generate_service as generate_service

    captured_events: list[dict] = []
    captured_payload: dict = {}

    async def _fake_run_pipeline(_request):
        raise RuntimeError("generate boom")

    async def _fake_notify(**kwargs):
        captured_events.append(kwargs)

    async def _fake_post_callback(callback_url, payload, timeout_seconds, service_secret, job_id):
        captured_payload.update(payload)

    monkeypatch.setattr(generate_service, "run_roadmap_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(generate_service, "_notify_pipeline_event_best_effort", _fake_notify)
    monkeypatch.setattr(generate_service, "_post_callback", _fake_post_callback)

    asyncio.run(
        generate_service.process_generate_request(
            job_id="generate-job-1",
            callback_url="https://example.com/internal",
            payload=_course_request(),
        )
    )

    assert captured_payload["status"] == "FAILED"
    assert [event["event_type"] for event in captured_events] == ["generate_started", "generate_completed"]
    assert captured_events[1]["status"] == "FAILED"
