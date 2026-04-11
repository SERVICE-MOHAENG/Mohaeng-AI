"""Pipeline stage webhook integration tests."""

from __future__ import annotations

import asyncio
import importlib
from datetime import date
from types import SimpleNamespace

from app.core.config import get_settings
from app.graph.chat.state import ChatState
from app.schemas.course import CourseRequest, CourseResponse, RegionDateRange
from app.schemas.enums import (
    ActivityPreference,
    BudgetRange,
    CompanionType,
    DestinationPreference,
    PacePreference,
    PlanningPreference,
    PriorityPreference,
    Region,
    TravelTheme,
)


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _course_request() -> CourseRequest:
    start = date(2026, 1, 1)
    end = date(2026, 1, 1)
    return CourseRequest(
        start_date=start,
        end_date=end,
        regions=[RegionDateRange(region=Region.SEOUL, start_date=start, end_date=end)],
        people_count=1,
        companion_type=[CompanionType.SOLO],
        travel_themes=[TravelTheme.CITY_TRIP],
        pace_preference=PacePreference.RELAXED,
        planning_preference=PlanningPreference.PLANNED,
        destination_preference=DestinationPreference.TOURIST_SPOTS,
        activity_preference=ActivityPreference.REST_FOCUSED,
        priority_preference=PriorityPreference.EFFICIENCY,
        budget_range=BudgetRange.MID,
    )


def _course_response() -> CourseResponse:
    today = date(2026, 1, 1)
    return CourseResponse(
        start_date=today,
        end_date=today,
        trip_days=1,
        nights=0,
        people_count=1,
        tags=[],
        title="Test title",
        summary="Test summary",
        itinerary=[],
        llm_commentary="Test commentary",
        next_action_suggestion=[],
    )


def _event_types(payloads: list[dict]) -> list[str]:
    event_types: list[str] = []
    for payload in payloads:
        event_type = next(field["value"] for field in payload["fields"] if field["name"] == "event_type")
        event_types.append(event_type)
    return event_types


def _fake_classify_intent_route(*args, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(intent_type="MODIFICATION", requested_action="ADD", target_scope="ITEM")


def _fake_parse_modification_intent(*args, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        op="ADD",
        target_day=1,
        target_index=2,
        search_keyword="cafe",
        needs_clarification=False,
        model_dump=lambda: {"op": "ADD", "target_day": 1, "target_index": 2, "reasoning": "test"},
    )


def _run_coroutine(coro) -> None:
    asyncio.run(coro)


def test_generate_service_emits_start_and_completion_webhooks(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    import app.services.generate_service as generate_service

    payloads: list[dict] = []

    async def _fake_notify(**kwargs) -> None:
        payloads.append(kwargs)

    async def _fake_pipeline(request):
        return _course_response()

    async def _fake_post_callback(**kwargs) -> None:
        return None

    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(generate_service, "notify_pipeline_event", _fake_notify)
    monkeypatch.setattr(generate_service, "notify_job_completed", _noop)
    monkeypatch.setattr(generate_service, "notify_timeout", _noop)
    monkeypatch.setattr(generate_service, "run_roadmap_pipeline", _fake_pipeline)
    monkeypatch.setattr(generate_service, "_post_callback", _fake_post_callback)

    asyncio.run(generate_service.process_generate_request("job-1", "https://example.com/callback", _course_request()))

    assert [item["event_type"] for item in payloads] == ["generate_started", "generate_completed"]


def test_analyze_intent_emits_routing_and_parse_webhooks(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    import app.services.webhook_notification as webhook

    analyze_intent = importlib.import_module("app.graph.chat.nodes.analyze_intent")
    payloads: list[dict] = []

    async def _fake_send(embed: dict) -> None:
        payloads.append(embed)

    monkeypatch.setattr(webhook, "_send_embed", _fake_send)
    monkeypatch.setattr(analyze_intent, "schedule_webhook", _run_coroutine)
    monkeypatch.setattr(analyze_intent, "_build_itinerary_table", lambda itinerary: "table")
    monkeypatch.setattr(analyze_intent, "_build_history_context", lambda history: "history")
    monkeypatch.setattr(analyze_intent, "_build_request_context", lambda request_context: "request")
    monkeypatch.setattr(analyze_intent, "_build_day_region_hints", lambda itinerary: {})
    monkeypatch.setattr(analyze_intent, "_format_day_region_context", lambda hints: "regions")
    monkeypatch.setattr(analyze_intent, "_classify_intent_route", _fake_classify_intent_route)
    monkeypatch.setattr(analyze_intent, "_parse_modification_intent", _fake_parse_modification_intent)

    state: ChatState = {
        "current_itinerary": {},
        "user_query": "Add a cafe to day 1",
        "session_history": [],
        "request_context": {},
    }
    result = analyze_intent.analyze_intent(state)

    assert result["intent_type"] == "MODIFICATION"
    assert _event_types(payloads) == ["chat_intent_routed", "chat_intent_parsed"]
