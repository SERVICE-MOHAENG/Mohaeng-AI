"""visit_time 정책 테스트."""

from __future__ import annotations

from app.core.visit_time_policy import VisitTimeOutputMode, apply_visit_time_policy


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


def test_apply_visit_time_policy_maps_sequence_to_hhmm_without_transit_warnings() -> None:
    places, warnings = apply_visit_time_policy(_places(), output_mode=VisitTimeOutputMode.HHMM)

    assert [place["visit_time"] for place in places] == ["09:00", "12:00", "14:00", "18:00", "20:00", "22:00", "23:00"]
    assert warnings == []


def test_apply_visit_time_policy_maps_sequence_to_section_labels() -> None:
    places, warnings = apply_visit_time_policy(_places(), output_mode=VisitTimeOutputMode.SECTION_EN)

    assert [place["visit_time"] for place in places] == [
        "MORNING",
        "LUNCH",
        "AFTERNOON",
        "DINNER",
        "EVENING",
        "NIGHT",
        "NIGHT",
    ]
    assert warnings == []
