"""로드맵 수정 실행 노드."""

from __future__ import annotations

import copy

from app.core.config import get_settings
from app.core.geo import GeoRectangle
from app.core.llm_router import Stage, invoke
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.chat.state import ChatState
from app.graph.chat.utils import build_diff_key, reorder_visit_sequence
from app.schemas.enums import ChatOperation, ChatStatus
from app.services.google_places_service import get_google_places_service
from app.services.place_rerank_service import select_place_id_for_chat

logger = get_logger(__name__)

_BBOX_MARGIN_KM = 10.0
_MAX_PLACES_PER_DAY = 10
_MIN_PLACES_PER_DAY = 1


def _day_points(day: dict) -> list[tuple[float, float]]:
    places = day.get("places", [])
    points: list[tuple[float, float]] = []
    for place in places:
        lat = place.get("latitude")
        lon = place.get("longitude")
        if lat is None or lon is None:
            continue
        points.append((float(lat), float(lon)))
    return points


def _day_bbox(day: dict) -> GeoRectangle | None:
    return GeoRectangle.from_points_with_margin_km(_day_points(day), margin_km=_BBOX_MARGIN_KM)


def _place_to_course_place(place, visit_sequence: int) -> dict:
    """Place 모델을 CoursePlace dict로 변환합니다."""
    return {
        "place_name": place.name,
        "place_id": place.place_id,
        "address": place.address,
        "latitude": place.geometry.latitude,
        "longitude": place.geometry.longitude,
        "place_url": place.url,
        "description": f"{place.name}에서 즐길 수 있는 대표 활동입니다.",
        "visit_sequence": visit_sequence,
        "visit_time": "",
    }


def _find_day(itinerary: dict, day_number: int) -> dict | None:
    """day_number에 해당하는 일자 항목을 찾습니다."""
    for day in itinerary.get("itinerary", []):
        if day.get("day_number") == day_number:
            return day
    return None


def _reorder_results_by_place_id(results: list, selected_place_id: str) -> list:
    selected_index = next(
        (index for index, place in enumerate(results) if place.place_id == selected_place_id),
        None,
    )
    if selected_index in (None, 0):
        return results
    return [results[selected_index], *results[:selected_index], *results[selected_index + 1 :]]


def _hard_filter_by_bbox(results: list, bbox: GeoRectangle) -> tuple[list, int]:
    filtered = [p for p in results if bbox.contains(p.geometry.latitude, p.geometry.longitude)]
    return filtered, max(0, len(results) - len(filtered))


async def mutate(state: ChatState) -> ChatState:
    """분석된 의도에 따라 일정 수정을 적용합니다."""
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

    if op in (ChatOperation.REPLACE, ChatOperation.REMOVE, ChatOperation.MOVE):
        if target_pos < 0 or target_pos >= len(places):
            return {**state, "error": f"{target_day_num}일차의 {target_index}번째 장소가 없습니다."}

    diff_keys: list[str] = []
    warnings: list[str] = state.get("warnings", [])
    search_results: list = []

    if op == ChatOperation.REPLACE:
        new_place, search_results, err = await _search_place(intent, day)
        if err:
            return {**state, "search_results": search_results, **err}
        places[target_pos] = _place_to_course_place(new_place, target_index)
        diff_keys.append(build_diff_key(target_day_num, target_index))

    elif op == ChatOperation.ADD:
        if len(places) >= _MAX_PLACES_PER_DAY:
            return {
                **state,
                "status": ChatStatus.REJECTED,
                "change_summary": "하루 일정에는 최대 10개 장소까지만 추가할 수 있습니다.",
            }
        if target_index < 1 or target_index > len(places) + 1:
            return {**state, "error": f"{target_day_num}일차의 {target_index}번째 위치에는 추가할 수 없습니다."}
        insert_pos = target_index - 1
        new_place, search_results, err = await _search_place(intent, day)
        if err:
            return {**state, "search_results": search_results, **err}
        places.insert(insert_pos, _place_to_course_place(new_place, 0))
        reorder_visit_sequence(places)
        diff_keys.append(build_diff_key(target_day_num, insert_pos + 1))

    elif op == ChatOperation.REMOVE:
        if len(places) <= _MIN_PLACES_PER_DAY:
            return {
                **state,
                "status": ChatStatus.REJECTED,
                "change_summary": "하루 일정은 최소 1개 이상 유지되어야 합니다.",
            }
        places.pop(target_pos)
        reorder_visit_sequence(places)
        diff_keys.append(build_diff_key(target_day_num, target_index))

    elif op == ChatOperation.MOVE:
        dest_day_num = intent.get("destination_day", target_day_num)
        if dest_day_num != target_day_num:
            return {
                **state,
                "status": ChatStatus.REJECTED,
                "change_summary": "일자 간 이동은 지원하지 않습니다. 같은 일자 내 순서만 변경 가능합니다.",
            }
        dest_index = max(1, intent.get("destination_index", 1))
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
            diff_keys.append(build_diff_key(target_day_num, 1))
            dest_places = dest_day.get("places", [])
            dest_pos = min(dest_pos, len(dest_places))
            dest_places.insert(dest_pos, moved)
            reorder_visit_sequence(dest_places)
            dest_day["places"] = dest_places
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
    """장소 후보를 검색하고 선택 결과를 메타데이터와 함께 반환합니다."""
    keyword = intent.get("search_keyword", "")
    if not keyword:
        return None, [], {"error": "검색 키워드가 없습니다."}

    settings = get_settings()
    min_rating = settings.GOOGLE_PLACES_MIN_RATING
    rerank_enabled = settings.GOOGLE_PLACES_LLM_RERANK_ENABLED
    rerank_max_candidates = settings.GOOGLE_PLACES_LLM_RERANK_MAX_CANDIDATES
    rerank_timeout_seconds = get_timeout_policy(settings).llm_timeout_seconds

    geo_filter_scope = "chat_day_bbox"
    geo_filter_fallback_unfiltered = False
    geo_filtered_out_count = 0

    day_bbox = _day_bbox(day)
    geo_filter_applied = day_bbox is not None

    try:
        service = get_google_places_service()
        results = await service.search(
            keyword,
            min_rating=min_rating,
            location_restriction=day_bbox,
        )

        if day_bbox is not None and results:
            results, filtered_out = _hard_filter_by_bbox(results, day_bbox)
            geo_filtered_out_count += filtered_out

        if not results and day_bbox is not None:
            geo_filter_fallback_unfiltered = True
            results = await service.search(
                keyword,
                min_rating=min_rating,
                location_restriction=None,
            )

        fallback_to_unfiltered = False
        if not results:
            fallback_to_unfiltered = True
            results = await service.search(
                keyword,
                min_rating=None,
                location_restriction=None,
            )

        logger.info(
            (
                "Chat place search result: min_rating_applied=%s fallback_to_unfiltered=%s candidate_count=%d "
                "geo_filter_applied=%s geo_filter_scope=%s "
                "geo_filter_fallback_unfiltered=%s geo_filtered_out_count=%d geo_missing_region_bbox=%s"
            ),
            min_rating is not None,
            fallback_to_unfiltered,
            len(results),
            geo_filter_applied,
            geo_filter_scope,
            geo_filter_fallback_unfiltered,
            geo_filtered_out_count,
            day_bbox is None,
        )
    except Exception as exc:
        logger.error("Google Places search failed: %s", exc)
        return None, [], {"error": "장소 검색에 실패했습니다."}

    search_results = [r.model_dump() for r in results]
    if not results:
        suggested = _suggest_alternative_keyword(keyword)
        return (
            None,
            search_results,
            {
                "status": ChatStatus.ASK_CLARIFICATION,
                "change_summary": f"'{keyword}' 검색 결과가 없습니다."
                + (f" '{suggested}'로 다시 검색해볼까요?" if suggested else ""),
                "suggested_keyword": suggested,
            },
        )

    if rerank_enabled and len(results) > 1:
        selected_place_id = await select_place_id_for_chat(
            keyword=keyword,
            candidates=[place.model_dump() for place in results[:rerank_max_candidates]],
            day=day,
            max_candidates=rerank_max_candidates,
            timeout_seconds=rerank_timeout_seconds,
        )
        if selected_place_id:
            results = _reorder_results_by_place_id(results, selected_place_id)
        logger.info(
            "Chat place rerank result: flow=chat batch_size=%d selected=%d missed=%d fallback_used=%s",
            min(rerank_max_candidates, len(results)),
            1 if selected_place_id else 0,
            0 if selected_place_id else 1,
            selected_place_id is None,
        )

    search_results = [r.model_dump() for r in results]
    return results[0], search_results, None


def _suggest_alternative_keyword(keyword: str) -> str | None:
    """검색 실패 시 LLM으로 상위 카테고리 키워드를 제안받습니다."""
    try:
        response = invoke(
            Stage.CHAT_KEYWORD_ASSIST,
            f"'{keyword}'의 상위 카테고리 키워드를 한 단어로 말해줘. 예: '오마카세' -> '일식'",
        )
        suggested = response.content.strip().strip("'\"")
        return suggested if suggested and suggested != keyword else None
    except Exception as exc:
        logger.warning("Alternative keyword suggestion failed: %s", exc)
        return None
