"""로드맵 장소명 한국어 정규화 테스트."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.core.config import get_settings
from app.graph.roadmap.nodes.finalize import _prepare_final_context
from app.graph.roadmap.nodes.translate import normalize_place_names


def _base_course_request() -> dict:
    return {
        "start_date": "2026-02-01",
        "end_date": "2026-02-02",
        "regions": [
            {
                "region": "SEOUL",
                "start_date": "2026-02-01",
                "end_date": "2026-02-02",
            }
        ],
        "people_count": 2,
        "companion_type": ["FAMILY"],
        "travel_themes": ["HEALING"],
        "pace_preference": "RELAXED",
        "planning_preference": "PLANNED",
        "destination_preference": "TOURIST_SPOTS",
        "activity_preference": "REST_FOCUSED",
        "priority_preference": "EFFICIENCY",
        "budget_range": "MID",
    }


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    get_settings.cache_clear()


def test_normalize_place_names_sets_korean_display_names(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    payloads: list[dict] = []

    async def _fake_ainvoke(stage, messages, timeout_seconds=None):
        payloads.append({"stage": stage, "messages": messages})
        return SimpleNamespace(
            content=json.dumps(
                {
                    "items": [
                        {"place_id": "place-1", "display_name": "런던 아이"},
                    ]
                },
                ensure_ascii=False,
            )
        )

    monkeypatch.setattr("app.graph.roadmap.nodes.translate.ainvoke", _fake_ainvoke)

    state = {
        "fetched_places": {
            "day-1": [
                {
                    "place_id": "place-1",
                    "name": "London Eye",
                    "address": "Lambeth, London",
                    "geometry": {"latitude": 51.5033, "longitude": -0.1195},
                },
                {
                    "place_id": "place-2",
                    "name": "경복궁",
                    "address": "서울 종로구",
                    "geometry": {"latitude": 37.5796, "longitude": 126.977},
                },
            ]
        }
    }

    result = asyncio.run(normalize_place_names(state))

    places = result["fetched_places"]["day-1"]
    assert places[0]["display_name"] == "런던 아이"
    assert places[0]["name"] == "London Eye"
    assert places[1]["display_name"] == "경복궁"
    assert payloads and payloads[0]["stage"].value == "ROADMAP_PLACE_TRANSLATE"


def test_normalize_place_names_falls_back_to_original_when_llm_fails(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    async def _failing_ainvoke(stage, messages, timeout_seconds=None):
        raise RuntimeError("translation failed")

    monkeypatch.setattr("app.graph.roadmap.nodes.translate.ainvoke", _failing_ainvoke)

    state = {
        "fetched_places": {
            "day-1": [
                {
                    "place_id": "place-1",
                    "name": "London Eye",
                    "address": "Lambeth, London",
                    "geometry": {"latitude": 51.5033, "longitude": -0.1195},
                }
            ]
        }
    }

    result = asyncio.run(normalize_place_names(state))

    places = result["fetched_places"]["day-1"]
    assert places[0]["display_name"] == "London Eye"


def test_prepare_final_context_uses_display_name_for_itinerary_output() -> None:
    state = {
        "course_request": _base_course_request(),
        "trip_days": 1,
        "slot_min": 1,
        "slot_max": 1,
        "skeleton_plan": [
            {
                "day_number": 1,
                "region": "SEOUL",
                "slots": [
                    {
                        "section": "오전",
                        "area": "중심가",
                        "keyword": "museum",
                    }
                ],
            }
        ],
        "fetched_places": {
            "day1_slot0": [
                {
                    "place_id": "place-1",
                    "name": "London Eye",
                    "display_name": "런던 아이",
                    "address": "Lambeth, London",
                    "geometry": {"latitude": 37.5796, "longitude": 126.977},
                    "url": None,
                }
            ]
        },
    }

    itinerary_context, daily_places = _prepare_final_context(state)

    assert "런던 아이" in itinerary_context
    assert daily_places[0]["places"][0]["place_name"] == "런던 아이"
    assert daily_places[0]["places"][0]["original_place_name"] == "London Eye"
