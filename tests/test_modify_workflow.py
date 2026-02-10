"""로드맵 수정 워크플로우 통합 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.enums import ModifyOperation, ModifyStatus
from app.schemas.modify import ModifyIntent


@pytest.fixture()
def sample_itinerary():
    """테스트용 로드맵 데이터."""
    return {
        "start_date": "2025-07-01",
        "end_date": "2025-07-02",
        "trip_days": 2,
        "nights": 1,
        "people_count": 2,
        "tags": ["맛집", "관광"],
        "title": "서울 여행",
        "summary": "서울 2일 여행",
        "itinerary": [
            {
                "day_number": 1,
                "daily_date": "2025-07-01",
                "places": [
                    {
                        "place_name": "경복궁",
                        "place_id": "place_001",
                        "address": "서울 종로구",
                        "latitude": 37.5796,
                        "longitude": 126.9770,
                        "place_url": None,
                        "description": "경복궁에서 즐기는 대표 활동입니다.",
                        "visit_sequence": 1,
                        "visit_time": "09:00",
                    },
                    {
                        "place_name": "스시 오마카세",
                        "place_id": "place_002",
                        "address": "서울 종로구",
                        "latitude": 37.5700,
                        "longitude": 126.9800,
                        "place_url": None,
                        "description": "스시 오마카세에서 즐기는 대표 활동입니다.",
                        "visit_sequence": 2,
                        "visit_time": "12:00",
                    },
                    {
                        "place_name": "북촌한옥마을",
                        "place_id": "place_003",
                        "address": "서울 종로구",
                        "latitude": 37.5826,
                        "longitude": 126.9831,
                        "place_url": None,
                        "description": "북촌한옥마을에서 즐기는 대표 활동입니다.",
                        "visit_sequence": 3,
                        "visit_time": "14:30",
                    },
                ],
            },
            {
                "day_number": 2,
                "daily_date": "2025-07-02",
                "places": [
                    {
                        "place_name": "남산타워",
                        "place_id": "place_004",
                        "address": "서울 용산구",
                        "latitude": 37.5512,
                        "longitude": 126.9882,
                        "place_url": None,
                        "description": "남산타워에서 즐기는 대표 활동입니다.",
                        "visit_sequence": 1,
                        "visit_time": "10:00",
                    },
                ],
            },
        ],
        "llm_commentary": "서울의 대표 명소를 둘러보는 코스입니다.",
        "next_action_suggestion": ["일정을 수정해주세요."],
    }


def _make_mock_intent(op: str = "REPLACE", target_day: int = 1, target_index: int = 2) -> str:
    """Mock LLM이 반환할 ModifyIntent JSON."""
    intent = ModifyIntent(
        op=ModifyOperation(op),
        target_day=target_day,
        target_index=target_index,
        search_keyword="라멘",
        reasoning="점심 식당을 라멘으로 교체 요청",
        is_compound=False,
        needs_clarification=False,
    )
    return json.dumps(intent.model_dump(), ensure_ascii=False)


def _make_mock_place():
    """Mock Google Places 검색 결과."""
    mock_place = MagicMock()
    mock_place.name = "멘야 하나비 라멘"
    mock_place.place_id = "place_new_001"
    mock_place.address = "서울 종로구 라멘길 1"
    mock_place.geometry.latitude = 37.5720
    mock_place.geometry.longitude = 126.9790
    mock_place.url = "https://maps.google.com/test"
    mock_place.rating = 4.5
    mock_place.user_ratings_total = 200
    mock_place.types = ["restaurant"]
    mock_place.model_dump.return_value = {
        "name": "멘야 하나비 라멘",
        "place_id": "place_new_001",
        "address": "서울 종로구 라멘길 1",
        "geometry": {"latitude": 37.5720, "longitude": 126.9790},
        "url": "https://maps.google.com/test",
        "rating": 4.5,
        "user_ratings_total": 200,
        "types": ["restaurant"],
    }
    return mock_place


@pytest.mark.asyncio
async def test_modify_replace_workflow(sample_itinerary):
    """REPLACE 시나리오 전체 워크플로우 통합 테스트."""
    mock_intent_response = MagicMock()
    mock_intent_response.content = _make_mock_intent()

    mock_respond_response = MagicMock()
    mock_respond_response.content = "1일차 점심을 '멘야 하나비 라멘'으로 변경했어요!"

    mock_llm = MagicMock()
    call_count = 0

    def _side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_intent_response
        return mock_respond_response

    mock_llm.invoke.side_effect = _side_effect

    mock_places_service = AsyncMock()
    mock_places_service.search.return_value = [_make_mock_place()]

    with (
        patch("app.graph.modify.nodes.analyze_intent.get_llm", return_value=mock_llm),
        patch("app.graph.modify.nodes.respond.get_llm", return_value=mock_llm),
        patch("app.graph.modify.nodes.mutate.get_google_places_service", return_value=mock_places_service),
    ):
        from app.graph.modify.workflow import compiled_modify_graph

        initial_state = {
            "current_itinerary": sample_itinerary,
            "user_query": "1일차 점심 라멘으로 바꿔줘",
            "session_history": [],
            "metadata": {},
        }

        result = await compiled_modify_graph.ainvoke(initial_state)

    assert result.get("error") is None
    assert result["status"] in (ModifyStatus.SUCCESS, ModifyStatus.SUCCESS.value)
    assert result.get("modified_itinerary") is not None
    assert len(result.get("diff_keys", [])) > 0

    modified_day1 = result["modified_itinerary"]["itinerary"][0]
    replaced_place = modified_day1["places"][1]
    assert replaced_place["place_name"] == "멘야 하나비 라멘"
    assert replaced_place["visit_sequence"] == 2

    assert result.get("change_summary")
