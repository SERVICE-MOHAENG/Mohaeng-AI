"""로드맵 수정 Operation 실행 노드."""

from __future__ import annotations

import copy

from app.core.logger import get_logger
from app.graph.modify.llm import get_llm
from app.graph.modify.state import ModifyState
from app.graph.modify.utils import (
    build_diff_key,
    haversine_distance,
    reorder_visit_sequence,
)
from app.schemas.enums import ModifyOperation, ModifyStatus
from app.services.google_places_service import get_google_places_service

logger = get_logger(__name__)

_RADIUS_KM = 10.0


def _day_center(day: dict) -> tuple[float, float]:
    """Day 내 장소들의 중심 좌표를 계산합니다."""
    places = day.get("places", [])
    coords = [
        (p["latitude"], p["longitude"])
        for p in places
        if p.get("latitude") is not None and p.get("longitude") is not None
    ]
    if not coords:
        return 0.0, 0.0
    avg_lat = sum(lat for lat, _ in coords) / len(coords)
    avg_lon = sum(lon for _, lon in coords) / len(coords)
    return avg_lat, avg_lon


def _place_to_course_place(place, visit_sequence: int) -> dict:
    """Place 모델을 CoursePlace dict로 변환합니다."""
    return {
        "place_name": place.name,
        "place_id": place.place_id,
        "address": place.address,
        "latitude": place.geometry.latitude,
        "longitude": place.geometry.longitude,
        "place_url": place.url,
        "description": place.name,
        "visit_sequence": visit_sequence,
        "visit_time": "",
    }


def _find_day(itinerary: dict, day_number: int) -> dict | None:
    """itinerary에서 day_number에 해당하는 Day를 찾습니다."""
    for day in itinerary.get("itinerary", []):
        if day.get("day_number") == day_number:
            return day
    return None


async def mutate(state: ModifyState) -> ModifyState:
    """Intent에 따라 로드맵 JSON을 수정합니다."""
    intent = state.get("intent")
    current_itinerary = state.get("current_itinerary")

    if not intent or not current_itinerary:
        return {**state, "error": "mutate에는 intent와 current_itinerary가 필요합니다."}

    op = intent["op"]
    target_day_num = intent["target_day"]
    target_index = intent["target_index"]

    itinerary = copy.deepcopy(current_itinerary)
    day = _find_day(itinerary, target_day_num)
    if not day:
        return {**state, "error": f"{target_day_num}일차를 찾을 수 없습니다."}

    places = day.get("places", [])
    target_pos = target_index - 1

    if op in (ModifyOperation.REPLACE, ModifyOperation.REMOVE, ModifyOperation.MOVE):
        if target_pos < 0 or target_pos >= len(places):
            return {**state, "error": f"{target_day_num}일차에 {target_index}번 장소가 없습니다."}

    diff_keys: list[str] = []
    warnings: list[str] = state.get("warnings", [])
    search_results: list = []

    if op == ModifyOperation.REPLACE:
        new_place, search_results, err = await _search_place(intent, day)
        if err:
            return {**state, "search_results": search_results, **err}
        places[target_pos] = _place_to_course_place(new_place, target_index)
        diff_keys.append(build_diff_key(target_day_num, target_index))

    elif op == ModifyOperation.ADD:
        insert_pos = min(target_pos, len(places))
        new_place, search_results, err = await _search_place(intent, day)
        if err:
            return {**state, "search_results": search_results, **err}
        places.insert(insert_pos, _place_to_course_place(new_place, 0))
        reorder_visit_sequence(places)
        diff_keys.append(build_diff_key(target_day_num, insert_pos + 1))

    elif op == ModifyOperation.REMOVE:
        places.pop(target_pos)
        reorder_visit_sequence(places)
        diff_keys.append(build_diff_key(target_day_num, target_index))

    elif op == ModifyOperation.MOVE:
        dest_day_num = intent.get("destination_day", target_day_num)
        dest_index = intent.get("destination_index", 1)
        dest_pos = dest_index - 1

        if dest_day_num == target_day_num:
            moved = places.pop(target_pos)
            dest_pos = min(dest_pos, len(places))
            places.insert(dest_pos, moved)
            reorder_visit_sequence(places)
            diff_keys.append(build_diff_key(target_day_num, dest_pos + 1))
        else:
            dest_day = _find_day(itinerary, dest_day_num)
            if not dest_day:
                return {**state, "error": f"{dest_day_num}일차를 찾을 수 없습니다."}
            moved = places.pop(target_pos)
            reorder_visit_sequence(places)
            dest_places = dest_day.get("places", [])
            dest_pos = min(dest_pos, len(dest_places))
            dest_places.insert(dest_pos, moved)
            reorder_visit_sequence(dest_places)
            diff_keys.append(build_diff_key(dest_day_num, dest_pos + 1))

    day["places"] = places

    return {
        **state,
        "modified_itinerary": itinerary,
        "diff_keys": diff_keys,
        "warnings": warnings,
        "search_results": search_results,
    }


async def _search_place(intent: dict, day: dict) -> tuple:
    """Google Places 검색 후 10km 반경 필터링을 수행합니다.

    Returns:
        (place, search_results, error_dict | None)
    """
    keyword = intent.get("search_keyword", "")
    if not keyword:
        return None, [], {"error": "검색 키워드가 없습니다."}

    try:
        service = get_google_places_service()
        results = await service.search(keyword)
    except Exception as exc:
        logger.error("Google Places 검색 실패: %s", exc)
        return None, [], {"error": "장소 검색에 실패했습니다."}

    search_results = [r.model_dump() for r in results]

    if not results:
        suggested = _suggest_alternative_keyword(keyword)
        return (
            None,
            search_results,
            {
                "status": ModifyStatus.ASK_CLARIFICATION,
                "change_summary": f"'{keyword}' 검색 결과가 없습니다."
                + (f" '{suggested}'(으)로 다시 검색해볼까요?" if suggested else ""),
                "suggested_keyword": suggested,
            },
        )

    center_lat, center_lon = _day_center(day)
    if center_lat != 0.0 or center_lon != 0.0:
        filtered = [
            p
            for p in results
            if haversine_distance(center_lat, center_lon, p.geometry.latitude, p.geometry.longitude) <= _RADIUS_KM
        ]
        if filtered:
            results = filtered

    return results[0], search_results, None


def _suggest_alternative_keyword(keyword: str) -> str | None:
    """LLM을 통해 검색 키워드의 상위 카테고리를 추출합니다."""
    try:
        response = get_llm().invoke(
            f"'{keyword}'의 상위 카테고리 키워드를 한 단어로 답하세요. 예: '오마카세' → '일식당'"
        )
        suggested = response.content.strip().strip("'\"")
        return suggested if suggested and suggested != keyword else None
    except Exception as exc:
        logger.warning("대안 키워드 추출 실패: %s", exc)
        return None
