"""로드맵 채팅 일차 간 재배치 정책 테스트."""

from __future__ import annotations

import asyncio
import importlib

from app.graph.chat.nodes.mutate import mutate
from app.schemas.enums import ChatStatus

analyze_module = importlib.import_module("app.graph.chat.nodes.analyze_intent")


def _place(day: int, sequence: int) -> dict:
    return {
        "place_name": f"{day}일차 장소 {sequence}",
        "place_id": f"place-{day}-{sequence}",
        "address": "서울 종로구",
        "latitude": 37.57 + day / 100 + sequence / 1000,
        "longitude": 126.97 + day / 100 + sequence / 1000,
        "place_url": "https://example.com/place",
        "place_category": "ATTRACTION",
        "description": "테스트 장소입니다.",
        "visit_sequence": sequence,
        "visit_time": f"0{8 + sequence}:00",
    }


def _day(day: int, count: int) -> dict:
    return {
        "day_number": day,
        "daily_date": f"2026-02-0{day}",
        "places": [_place(day, sequence) for sequence in range(1, count + 1)],
    }


def _itinerary(day_counts: tuple[int, ...] = (2, 2)) -> dict:
    return {
        "start_date": "2026-02-01",
        "end_date": f"2026-02-0{len(day_counts)}",
        "trip_days": len(day_counts),
        "nights": len(day_counts) - 1,
        "people_count": 2,
        "tags": ["테스트"],
        "title": "테스트 여행",
        "summary": "테스트 일정입니다.",
        "planning_preference": "PLANNED",
        "itinerary": [_day(index, count) for index, count in enumerate(day_counts, start=1)],
    }


def test_mutate_allows_cross_day_move_and_marks_both_days() -> None:
    state = {
        "current_itinerary": _itinerary(),
        "intent": {
            "op": "MOVE",
            "target_scope": "ITEM",
            "target_day": 2,
            "target_index": 1,
            "destination_day": 1,
            "destination_index": 3,
            "search_keyword": None,
            "reasoning": "테스트",
            "is_compound": False,
            "needs_clarification": False,
        },
    }

    result = asyncio.run(mutate(state))
    days = result["modified_itinerary"]["itinerary"]

    assert [place["place_id"] for place in days[0]["places"]] == ["place-1-1", "place-1-2", "place-2-1"]
    assert [place["place_id"] for place in days[1]["places"]] == ["place-2-2"]
    assert [place["visit_sequence"] for place in days[0]["places"]] == [1, 2, 3]
    assert [place["visit_sequence"] for place in days[1]["places"]] == [1]
    assert result["diff_keys"] == ["day1_place1", "day1_place2", "day1_place3", "day2_place1"]


def test_mutate_rejects_cross_day_move_when_source_day_would_be_empty() -> None:
    state = {
        "current_itinerary": _itinerary((2, 1)),
        "intent": {
            "op": "MOVE",
            "target_scope": "ITEM",
            "target_day": 2,
            "target_index": 1,
            "destination_day": 1,
            "destination_index": 1,
            "search_keyword": None,
            "reasoning": "테스트",
            "is_compound": False,
            "needs_clarification": False,
        },
    }

    result = asyncio.run(mutate(state))

    assert result["status"] == ChatStatus.REJECTED
    assert "최소 1개" in result["change_summary"]


def test_mutate_swaps_day_places_without_changing_day_metadata() -> None:
    itinerary = _itinerary()
    original_day1_date = itinerary["itinerary"][0]["daily_date"]
    original_day2_date = itinerary["itinerary"][1]["daily_date"]
    state = {
        "current_itinerary": itinerary,
        "intent": {
            "op": "REPLACE",
            "target_scope": "DAY_PLACES",
            "target_day": 1,
            "target_index": 1,
            "destination_day": 2,
            "destination_index": None,
            "search_keyword": None,
            "reasoning": "테스트",
            "is_compound": False,
            "needs_clarification": False,
        },
    }

    result = asyncio.run(mutate(state))
    day1, day2 = result["modified_itinerary"]["itinerary"]

    assert day1["day_number"] == 1
    assert day1["daily_date"] == original_day1_date
    assert [place["place_id"] for place in day1["places"]] == ["place-2-1", "place-2-2"]
    assert day2["day_number"] == 2
    assert day2["daily_date"] == original_day2_date
    assert [place["place_id"] for place in day2["places"]] == ["place-1-1", "place-1-2"]
    assert result["diff_keys"] == ["day1_place1", "day1_place2", "day2_place1", "day2_place2"]


def test_mutate_optimizes_single_day_route_and_marks_all_places() -> None:
    itinerary = _itinerary((4,))
    day = itinerary["itinerary"][0]
    day["places"] = [
        {
            **_place(1, 1),
            "place_name": "museum",
            "place_id": "museum",
            "place_category": "CULTURE",
            "latitude": 37.5000,
            "longitude": 127.0000,
        },
        {
            **_place(1, 2),
            "place_name": "far park",
            "place_id": "far-park",
            "place_category": "NATURE",
            "latitude": 37.5000,
            "longitude": 127.0900,
        },
        {
            **_place(1, 3),
            "place_name": "lunch",
            "place_id": "lunch",
            "place_category": "FOOD",
            "latitude": 37.5000,
            "longitude": 127.0200,
        },
        {
            **_place(1, 4),
            "place_name": "near gallery",
            "place_id": "near-gallery",
            "place_category": "ATTRACTION",
            "latitude": 37.5000,
            "longitude": 127.0300,
        },
    ]
    state = {
        "current_itinerary": itinerary,
        "intent": {
            "op": "MOVE",
            "target_scope": "DAY_OPTIMIZE",
            "target_day": 1,
            "target_index": 1,
            "destination_day": None,
            "destination_index": None,
            "search_keyword": None,
            "reasoning": "테스트",
            "is_compound": False,
            "needs_clarification": False,
        },
    }

    result = asyncio.run(mutate(state))
    places = result["modified_itinerary"]["itinerary"][0]["places"]

    assert [place["place_id"] for place in places] == ["far-park", "museum", "lunch", "near-gallery"]
    assert [place["visit_sequence"] for place in places] == [1, 2, 3, 4]
    assert result["diff_keys"] == ["day1_place1", "day1_place2", "day1_place3", "day1_place4"]
    assert "식사 일정은 유지" in result["change_summary"]
    assert places[2]["place_category"] == "FOOD"


def test_mutate_day_optimize_keeps_order_when_coordinates_are_missing() -> None:
    itinerary = _itinerary((3,))
    day = itinerary["itinerary"][0]
    day["places"] = [
        {**_place(1, 1), "place_name": "A", "place_id": "A", "place_category": "ATTRACTION"},
        {
            **_place(1, 2),
            "place_name": "B",
            "place_id": "B",
            "place_category": "ATTRACTION",
            "latitude": None,
            "longitude": None,
        },
        {**_place(1, 3), "place_name": "C", "place_id": "C", "place_category": "ATTRACTION"},
    ]
    state = {
        "current_itinerary": itinerary,
        "intent": {
            "op": "MOVE",
            "target_scope": "DAY_OPTIMIZE",
            "target_day": 1,
            "target_index": 1,
            "destination_day": None,
            "destination_index": None,
            "search_keyword": None,
            "reasoning": "테스트",
            "is_compound": False,
            "needs_clarification": False,
        },
    }

    result = asyncio.run(mutate(state))
    places = result["modified_itinerary"]["itinerary"][0]["places"]

    assert [place["place_id"] for place in places] == ["A", "B", "C"]
    assert "좌표" in result["warnings"][0]
    assert "기존 순서를 유지" in result["change_summary"]


def test_analyze_intent_structures_clear_day_places_swap_without_llm(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary(),
            "user_query": "1일차랑 2일차 일정 바꿔줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["intent"]["op"] == "REPLACE"
    assert result["intent"]["target_scope"] == "DAY_PLACES"
    assert result["intent"]["target_day"] == 1
    assert result["intent"]["destination_day"] == 2


def test_analyze_intent_structures_day_optimize_without_llm(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((4, 2)),
            "user_query": "1일차 전체 일정 최적화해줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["intent"]["op"] == "MOVE"
    assert result["intent"]["target_scope"] == "DAY_OPTIMIZE"
    assert result["intent"]["target_day"] == 1
    assert result["intent"]["destination_day"] is None


def test_analyze_intent_requests_clarification_for_ambiguous_day_optimize(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((2, 2)),
            "user_query": "동선 정리해줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["status"] == ChatStatus.ASK_CLARIFICATION
    assert "일차" in result["change_summary"]


def test_analyze_intent_keeps_general_chat_for_route_question_without_optimize_verb(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((2, 2)),
            "user_query": "이 일정 동선이 왜 이렇게 됐어?",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["intent_type"] == "GENERAL_CHAT"


def test_analyze_intent_rejects_multi_day_or_global_optimize_request(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((2, 2)),
            "user_query": "전체 일정 최적화해줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["status"] == ChatStatus.REJECTED
    assert "전체 일정 동선 최적화" in result["change_summary"]


def test_analyze_intent_structures_english_day_optimize_without_llm(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((2, 2, 2)),
            "user_query": "optimize route for first day",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["intent"]["op"] == "MOVE"
    assert result["intent"]["target_scope"] == "DAY_OPTIMIZE"
    assert result["intent"]["target_day"] == 1


def test_analyze_intent_rejects_date_change_request(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary(),
            "user_query": "여행 날짜를 내일로 바꿔줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["status"] == ChatStatus.REJECTED
    assert "재구성" in result["change_summary"]


def test_analyze_intent_structures_relative_day_swap_without_llm(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary((2, 2, 2)),
            "user_query": "첫날 코스와 마지막 날 코스를 서로 바꿔줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["intent"]["op"] == "REPLACE"
    assert result["intent"]["target_scope"] == "DAY_PLACES"
    assert result["intent"]["target_day"] == 1
    assert result["intent"]["destination_day"] == 3


def test_analyze_intent_requests_clarification_when_destination_position_is_missing(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(analyze_module, "invoke", _raise)

    result = analyze_module.analyze_intent(
        {
            "current_itinerary": _itinerary(),
            "user_query": "2일차 첫 번째 장소를 1일차로 옮겨줘",
            "session_history": [],
            "request_context": {},
        }
    )

    assert result["status"] == ChatStatus.ASK_CLARIFICATION
    assert "모호" in result["change_summary"] or "알려주세요" in result["change_summary"]
