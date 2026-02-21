"""Chat 스키마 계약 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest


def _base_payload() -> dict:
    return {
        "job_id": "chat-job-1",
        "callback_url": "https://example.com/internal",
        "companion_type": "FAMILY",
        "travel_themes": ["HEALING"],
        "pace_preference": "RELAXED",
        "planning_preference": "PLANNED",
        "destination_preference": "TOURIST_SPOTS",
        "activity_preference": "REST_FOCUSED",
        "priority_preference": "EFFICIENCY",
        "budget_range": "MID",
        "user_query": "1일차 2번째 장소 바꿔줘",
        "session_history": [],
        "current_itinerary": {
            "start_date": "2026-02-01",
            "end_date": "2026-02-02",
            "trip_days": 2,
            "nights": 1,
            "people_count": 2,
            "tags": ["가족", "힐링"],
            "title": "서울 여행",
            "summary": "가볍게 즐기는 1박 2일",
            "planning_preference": "PLANNED",
            "itinerary": [
                {
                    "day_number": 1,
                    "daily_date": "2026-02-01",
                    "places": [
                        {
                            "place_name": "경복궁",
                            "place_id": "test-place-id",
                            "address": "서울 종로구",
                            "latitude": 37.579617,
                            "longitude": 126.977041,
                            "place_url": "https://example.com/place",
                            "description": "고궁 산책",
                            "visit_sequence": 1,
                            "visit_time": "09:00",
                        }
                    ],
                }
            ],
        },
    }


def test_chat_request_accepts_context_fields() -> None:
    request = ChatRequest.model_validate(_base_payload())
    assert request.companion_type == "FAMILY"
    assert request.travel_themes == ["HEALING"]
    assert request.budget_range == "MID"


def test_chat_request_requires_context_fields() -> None:
    payload = _base_payload()
    payload.pop("companion_type")

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)
