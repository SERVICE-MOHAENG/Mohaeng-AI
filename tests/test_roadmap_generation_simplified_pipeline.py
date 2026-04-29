"""로드맵 생성 단순화 파이프라인 테스트."""

from __future__ import annotations

from app.graph.roadmap.nodes.finalize import _prepare_final_context, _visit_time_from_section
from app.graph.roadmap.workflow import compiled_roadmap_graph


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
    }


def test_roadmap_workflow_skips_place_name_normalization() -> None:
    graph = compiled_roadmap_graph.get_graph()
    node_names = set(graph.nodes)
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert "normalize_place_names" not in node_names
    assert ("generate_skeleton", "fetch_places_from_slots") in edges
    assert ("fetch_places_from_slots", "synthesize_final_roadmap") in edges


def test_visit_time_from_section_uses_static_hhmm_mapping() -> None:
    assert _visit_time_from_section("MORNING") == "09:00"
    assert _visit_time_from_section("LUNCH") == "12:00"
    assert _visit_time_from_section("AFTERNOON") == "14:00"
    assert _visit_time_from_section("DINNER") == "18:00"
    assert _visit_time_from_section("EVENING") == "20:00"
    assert _visit_time_from_section("NIGHT") == "22:00"
    assert _visit_time_from_section("unknown") == "09:00"


def test_prepare_final_context_uses_original_place_name_and_static_visit_time() -> None:
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
                        "section": "LUNCH",
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
                    "address": "Lambeth, London",
                    "geometry": {"latitude": 37.5796, "longitude": 126.977},
                    "url": None,
                }
            ]
        },
    }

    itinerary_context, daily_places = _prepare_final_context(state)

    place = daily_places[0]["places"][0]
    assert "London Eye" in itinerary_context
    assert place["place_name"] == "London Eye"
    assert place["original_place_name"] == "London Eye"
    assert place["visit_time"] == "12:00"
