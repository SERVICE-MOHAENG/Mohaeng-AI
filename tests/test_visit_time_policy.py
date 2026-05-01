"""visit_time 정책 테스트."""

from __future__ import annotations

import asyncio
import importlib

from app.core.visit_time_policy import VisitTimeOutputMode, apply_visit_time_policy
from app.schemas.enums import PlanningPreference


def _places() -> list[dict]:
    return [
        {"place_name": "A", "visit_sequence": 1, "latitude": 33.5, "longitude": 126.5},
        {"place_name": "B", "visit_sequence": 2, "latitude": 33.4, "longitude": 126.2},
        {"place_name": "C", "visit_sequence": 3, "latitude": 33.3, "longitude": 126.0},
        {"place_name": "D", "visit_sequence": 4, "latitude": 33.2, "longitude": 125.8},
        {"place_name": "E", "visit_sequence": 5, "latitude": 33.1, "longitude": 125.6},
        {"place_name": "F", "visit_sequence": 6, "latitude": 33.0, "longitude": 125.4},
        {"place_name": "G", "visit_sequence": 7, "latitude": 32.9, "longitude": 125.2},
    ]


def _ten_places() -> list[dict]:
    return [{"place_name": chr(65 + index), "visit_sequence": index + 1} for index in range(10)]


def test_apply_visit_time_policy_uses_even_hhmm_fallback_without_transit_warnings() -> None:
    places, warnings = apply_visit_time_policy(_places(), output_mode=VisitTimeOutputMode.HHMM)

    assert [place["visit_time"] for place in places] == [
        "09:00",
        "11:08",
        "13:16",
        "15:24",
        "17:32",
        "19:40",
        "21:48",
    ]
    assert warnings == []


def test_apply_visit_time_policy_maps_fallback_to_section_labels() -> None:
    places, warnings = apply_visit_time_policy(_places(), output_mode=VisitTimeOutputMode.SECTION_EN)

    assert [place["visit_time"] for place in places] == [
        "MORNING",
        "LUNCH",
        "LUNCH",
        "AFTERNOON",
        "AFTERNOON",
        "DINNER",
        "EVENING",
    ]
    assert warnings == []


def test_apply_visit_time_policy_does_not_clamp_eighth_to_tenth_hhmm_slots() -> None:
    places, warnings = apply_visit_time_policy(_ten_places(), output_mode=VisitTimeOutputMode.HHMM)

    assert [place["visit_time"] for place in places] == [
        "09:00",
        "10:30",
        "12:00",
        "13:30",
        "15:00",
        "16:30",
        "18:00",
        "19:30",
        "21:00",
        "22:30",
    ]
    assert warnings == []


def test_apply_visit_time_policy_uses_valid_llm_proposals_for_planned_output() -> None:
    places, warnings = apply_visit_time_policy(
        _places()[:3],
        day_number=1,
        llm_proposals_by_sequence={1: "08:30", 2: "12:15", 3: "24:00"},
        output_mode=VisitTimeOutputMode.HHMM,
    )

    assert [place["visit_time"] for place in places] == ["08:30", "12:15", "24:00"]
    assert warnings == []


def test_apply_visit_time_policy_rejects_out_of_range_or_decreasing_llm_proposals() -> None:
    places, warnings = apply_visit_time_policy(
        _places()[:4],
        day_number=2,
        llm_proposals_by_sequence={1: "07:59", 2: "10:00", 3: "09:30", 4: "24:01"},
        output_mode=VisitTimeOutputMode.HHMM,
    )

    assert [place["visit_time"] for place in places] == ["09:00", "10:00", "16:30", "20:15"]
    assert len(warnings) == 3


def test_propose_visit_time_skips_llm_for_spontaneous_itinerary(monkeypatch) -> None:
    async def _unexpected_call(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("SPONTANEOUS should not call visit time LLM")

    propose_module = importlib.import_module("app.graph.chat.nodes.propose_visit_time")
    monkeypatch.setattr(propose_module, "propose_visit_times_for_days", _unexpected_call)

    state = {
        "modified_itinerary": {
            "planning_preference": PlanningPreference.SPONTANEOUS,
            "itinerary": [{"day_number": 1, "places": _places()[:1]}],
        },
        "diff_keys": ["day1_place1"],
    }

    result = asyncio.run(propose_module.propose_visit_time(state))

    assert result["visit_time_proposals"] == {}
