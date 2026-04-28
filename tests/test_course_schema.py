"""CourseRequest 스키마 계약 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.course import CourseRequest


def _base_payload() -> dict:
    return {
        "start_date": "2026-02-01",
        "end_date": "2026-02-08",
        "regions": [
            {"region": "SEOUL", "start_date": "2026-02-01", "end_date": "2026-02-08"},
        ],
        "people_count": 2,
        "companion_type": ["FAMILY"],
        "travel_themes": ["HEALING"],
        "pace_preference": "RELAXED",
        "planning_preference": "PLANNED",
        "destination_preference": "TOURIST_SPOTS",
        "activity_preference": "REST_FOCUSED",
        "priority_preference": "EFFICIENCY",
    }


def test_course_request_accepts_up_to_eight_days_and_regions() -> None:
    payload = _base_payload()
    payload["regions"] = [
        {"region": "SEOUL", "start_date": "2026-02-01", "end_date": "2026-02-03"},
        {"region": "BUSAN", "start_date": "2026-02-04", "end_date": "2026-02-08"},
    ]

    request = CourseRequest.model_validate(payload)

    assert len(request.regions) == 2
    assert (request.end_date - request.start_date).days + 1 == 8


def test_course_request_rejects_more_than_eight_days() -> None:
    payload = _base_payload()
    payload["end_date"] = "2026-02-09"
    payload["regions"] = [
        {"region": "SEOUL", "start_date": "2026-02-01", "end_date": "2026-02-09"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        CourseRequest.model_validate(payload)

    assert "최대 8일" in str(exc_info.value)


def test_course_request_rejects_more_than_eight_regions() -> None:
    payload = _base_payload()
    payload["end_date"] = "2026-02-08"
    payload["regions"] = [
        {
            "region": "SEOUL",
            "start_date": "2026-02-01",
            "end_date": "2026-02-01",
        }
        for index in range(1, 10)
    ]

    with pytest.raises(ValidationError) as exc_info:
        CourseRequest.model_validate(payload)

    assert "at most 8 items" in str(exc_info.value) or "최대 8" in str(exc_info.value)
