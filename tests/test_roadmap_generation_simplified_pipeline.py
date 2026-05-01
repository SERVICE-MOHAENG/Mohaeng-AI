"""로드맵 생성 단순화 파이프라인 테스트."""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser

from app.graph.roadmap.nodes.finalize import (
    _build_summary_prompt_messages,
    _prepare_final_context,
)
from app.graph.roadmap.nodes.skeleton import _build_segment_prompt
from app.graph.roadmap.workflow import compiled_roadmap_graph
from app.schemas.course import CourseRequest, CourseResponseLLMOutput, RegionDateRange
from app.schemas.skeleton import SkeletonPlan


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


def test_prepare_final_context_uses_original_place_name_and_visit_time_policy() -> None:
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
                    "primary_type": "tourist_attraction",
                    "types": ["tourist_attraction", "point_of_interest"],
                }
            ]
        },
    }

    itinerary_context, daily_places = _prepare_final_context(state)

    place = daily_places[0]["places"][0]
    assert "London Eye" in itinerary_context
    assert place["place_name"] == "London Eye"
    assert place["original_place_name"] == "London Eye"
    assert place["place_category"] == "ATTRACTION"
    assert "primary_type" not in place
    assert place["visit_time"] == "09:00"


def test_prepare_final_context_allows_missing_primary_type() -> None:
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
                        "section": "MORNING",
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
                    "name": "경복궁",
                    "address": "서울 종로구",
                    "geometry": {"latitude": 37.5796, "longitude": 126.977},
                    "url": None,
                    "types": ["unknown_type"],
                }
            ]
        },
    }

    _, daily_places = _prepare_final_context(state)

    place = daily_places[0]["places"][0]
    assert place["place_name"] == "경복궁"
    assert place["place_category"] == "OTHER"
    assert "primary_type" not in place


def test_prepare_final_context_reorders_places_and_recalculates_planned_visit_time() -> None:
    state = {
        "course_request": _base_course_request(),
        "trip_days": 1,
        "slot_min": 3,
        "slot_max": 3,
        "skeleton_plan": [
            {
                "day_number": 1,
                "region": "SEOUL",
                "slots": [
                    {"section": "MORNING", "area": "중심가", "keyword": "a"},
                    {"section": "AFTERNOON", "area": "중심가", "keyword": "b"},
                    {"section": "EVENING", "area": "중심가", "keyword": "c"},
                ],
            }
        ],
        "fetched_places": {
            "day1_slot0": [
                {
                    "place_id": "place-a",
                    "name": "A",
                    "address": "서울",
                    "geometry": {"latitude": 37.5, "longitude": 127.0},
                    "primary_type": "museum",
                    "types": ["museum"],
                }
            ],
            "day1_slot1": [
                {
                    "place_id": "place-b",
                    "name": "B",
                    "address": "서울",
                    "geometry": {"latitude": 37.5, "longitude": 127.09},
                    "primary_type": "park",
                    "types": ["park"],
                }
            ],
            "day1_slot2": [
                {
                    "place_id": "place-c",
                    "name": "C",
                    "address": "서울",
                    "geometry": {"latitude": 37.5, "longitude": 127.01},
                    "primary_type": "shopping_mall",
                    "types": ["shopping_mall"],
                }
            ],
        },
    }

    itinerary_context, daily_places = _prepare_final_context(state)

    places = daily_places[0]["places"]
    assert [place["place_name"] for place in places] == ["A", "C", "B"]
    assert [place["visit_sequence"] for place in places] == [1, 2, 3]
    assert [place["visit_time"] for place in places] == ["09:00", "14:00", "19:00"]
    assert "#2" in itinerary_context
    assert "C" in itinerary_context


def test_prepare_final_context_uses_hhmm_baseline_for_spontaneous_visit_time() -> None:
    request = _base_course_request()
    request["planning_preference"] = "SPONTANEOUS"
    state = {
        "course_request": request,
        "trip_days": 1,
        "slot_min": 1,
        "slot_max": 1,
        "skeleton_plan": [
            {
                "day_number": 1,
                "region": "SEOUL",
                "slots": [{"section": "LUNCH", "area": "중심가", "keyword": "restaurant"}],
            }
        ],
        "fetched_places": {
            "day1_slot0": [
                {
                    "place_id": "food-1",
                    "name": "식당",
                    "address": "서울",
                    "geometry": {"latitude": 37.5, "longitude": 127.0},
                    "primary_type": "restaurant",
                    "types": ["restaurant"],
                }
            ]
        },
    }

    _, daily_places = _prepare_final_context(state)

    place = daily_places[0]["places"][0]
    assert place["place_category"] == "FOOD"
    assert place["visit_time"] == "09:00"


def test_segment_prompt_prioritizes_user_notes_when_present() -> None:
    request = CourseRequest.model_validate(
        {
            **_base_course_request(),
            "notes": "조용한 동선으로 구성하고 붐비는 관광지는 제외해 주세요.",
        }
    )
    segment = RegionDateRange.model_validate(request.regions[0].model_dump())
    parser = PydanticOutputParser(pydantic_object=SkeletonPlan)

    messages = _build_segment_prompt(
        request=request,
        segment=segment,
        segment_days=2,
        slot_min=4,
        slot_max=5,
        slot_targets=[5, 4],
        parser=parser,
    )

    system_content = messages[0].content
    user_content = messages[1].content

    assert "최우선 사용자 메모" in user_content
    assert "조용한 동선으로 구성하고 붐비는 관광지는 제외해 주세요." in user_content
    assert "다른 일반 선호값보다 우선해서 해석" in system_content
    assert "일반 선호보다 먼저 반영" in user_content


def test_finalize_summary_prompt_prioritizes_user_notes() -> None:
    parser = PydanticOutputParser(pydantic_object=CourseResponseLLMOutput)

    messages = _build_summary_prompt_messages(
        course_request_payload={**_base_course_request(), "notes": "전통시장과 로컬 식당을 꼭 포함해 주세요."},
        itinerary_context="\nDay 1 (2026-02-01):\n- #1 09:00 경복궁",
        priority_notes="전통시장과 로컬 식당을 꼭 포함해 주세요.",
        parser=parser,
    )

    system_content = messages[0].content
    user_content = messages[1].content

    assert "최우선 사용자 메모" in user_content
    assert "전통시장과 로컬 식당을 꼭 포함해 주세요." in user_content
    assert "title, summary, tags, llm_commentary 전반에서 가장 먼저 반영" in system_content
    assert "가장 중요한 제약으로 간주" in user_content
