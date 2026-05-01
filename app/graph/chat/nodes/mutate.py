"""로드맵 수정 실행 노드."""

from __future__ import annotations

import copy

from app.core.config import get_settings
from app.core.geo import GeoRectangle
from app.core.job_log_context import append_job_log
from app.core.llm_router import Stage, invoke
from app.core.logger import get_logger
from app.core.route_optimizer import optimize_daily_route
from app.core.timeout_policy import get_timeout_policy
from app.graph.chat.nodes.analyze_intent import extract_region_hint_from_address
from app.graph.chat.state import ChatState
from app.graph.chat.utils import build_diff_key, reorder_visit_sequence
from app.schemas.course import DAILY_ITINERARY_MAX_PLACES, DAILY_ITINERARY_MIN_PLACES
from app.schemas.enums import ChatOperation, ChatStatus
from app.services.google_places_service import get_google_places_service
from app.services.place_rerank_service import select_place_id_for_chat

logger = get_logger(__name__)

_BBOX_MARGIN_KM = 10.0
_MAX_PLACES_PER_DAY = DAILY_ITINERARY_MAX_PLACES
_MIN_PLACES_PER_DAY = DAILY_ITINERARY_MIN_PLACES


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


def _day_region_hint(day: dict) -> str:
    """day의 첫 번째 장소 주소에서 지역 힌트를 추출합니다."""
    for place in day.get("places", []):
        hint = extract_region_hint_from_address(str(place.get("address") or ""))
        if hint:
            return hint
    return ""


def _place_to_course_place(place, visit_sequence: int) -> dict:
    """Place 모델을 CoursePlace dict로 변환합니다."""
    return {
        "place_name": place.name,
        "place_id": place.place_id,
        "address": place.address,
        "latitude": place.geometry.latitude,
        "longitude": place.geometry.longitude,
        "place_url": place.url,
        "place_category": place.place_category,
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


def _build_day_diff_keys(day: dict) -> list[str]:
    """일차에 포함된 모든 장소 카드 diff key를 생성합니다."""
    day_number = day.get("day_number")
    if not isinstance(day_number, int):
        return []
    return [build_diff_key(day_number, index) for index in range(1, len(day.get("places", [])) + 1)]


def _has_missing_coordinate(place: dict) -> bool:
    lat = place.get("latitude")
    lon = place.get("longitude")
    try:
        return lat is None or lon is None or not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180)
    except (TypeError, ValueError):
        return True


def _sort_diff_keys(diff_keys: list[str]) -> list[str]:
    """diff key를 day, place 순서로 정렬하고 중복을 제거합니다."""
    parsed: list[tuple[int, int, str]] = []
    fallback: list[str] = []
    for key in dict.fromkeys(diff_keys):
        try:
            day_part, place_part = key.split("_", 1)
            parsed.append((int(day_part[3:]), int(place_part[5:]), key))
        except Exception:
            fallback.append(key)
    return [key for _, _, key in sorted(parsed)] + fallback


def _reorder_results_by_place_id(results: list, selected_place_id: str) -> list:
    selected_index = next(
        (index for index, place in enumerate(results) if place.place_id == selected_place_id),
        None,
    )
    if selected_index in (None, 0):
        return results
    return [results[selected_index], *results[:selected_index], *results[selected_index + 1 :]]


def _hard_filter_by_bbox(results: list, bbox: GeoRectangle) -> tuple[list, int]:
    return bbox.filter_places(results)


async def mutate(state: ChatState) -> ChatState:
    """분석된 의도에 따라 일정 수정을 적용합니다."""
    intent = state.get("intent")
    current_itinerary = state.get("current_itinerary")

    if not intent or not current_itinerary:
        return {**state, "error": "mutate에는 intent와 current_itinerary가 필요합니다."}

    op = intent["op"]
    target_scope = intent.get("target_scope", "ITEM")
    target_day_num = intent["target_day"]
    target_index = intent["target_index"]

    itinerary = copy.deepcopy(current_itinerary)
    day = _find_day(itinerary, target_day_num)
    if not day:
        return {**state, "error": f"{target_day_num}일차를 찾을 수 없습니다."}

    places = day.get("places", [])
    target_pos = target_index - 1

    if op in (ChatOperation.REPLACE, ChatOperation.REMOVE, ChatOperation.MOVE) and target_scope not in (
        "DAY_PLACES",
        "DAY_OPTIMIZE",
    ):
        if target_pos < 0 or target_pos >= len(places):
            return {**state, "error": f"{target_day_num}일차의 {target_index}번째 장소가 없습니다."}

    diff_keys: list[str] = []
    warnings: list[str] = state.get("warnings", [])
    search_results: list = []

    if op == ChatOperation.REPLACE and target_scope == "DAY_PLACES":
        dest_day_num = intent.get("destination_day")
        if not dest_day_num:
            return {
                **state,
                "status": ChatStatus.ASK_CLARIFICATION,
                "change_summary": "교체할 두 일차를 모두 알려주세요. 예: '1일차랑 2일차 일정 바꿔줘'",
            }
        dest_day = _find_day(itinerary, dest_day_num)
        if not dest_day:
            return {**state, "error": f"{dest_day_num}일차를 찾을 수 없습니다."}

        day["places"], dest_day["places"] = dest_day.get("places", []), day.get("places", [])
        reorder_visit_sequence(day["places"])
        reorder_visit_sequence(dest_day["places"])
        diff_keys.extend(_build_day_diff_keys(day))
        diff_keys.extend(_build_day_diff_keys(dest_day))
        change_summary = f"{target_day_num}일차와 {dest_day_num}일차에 배치된 장소 일정을 서로 바꿨습니다."

    elif op == ChatOperation.REPLACE:
        new_place, search_results, err = await _search_place(intent, day)
        if err:
            return {**state, "search_results": search_results, **err}
        places[target_pos] = _place_to_course_place(new_place, target_index)
        diff_keys.append(build_diff_key(target_day_num, target_index))
        change_summary = f"{target_day_num}일차 {target_index}번째 장소를 새 장소로 교체했습니다."

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
        change_summary = f"{target_day_num}일차 {insert_pos + 1}번째 위치에 새 장소를 추가했습니다."

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
        change_summary = f"{target_day_num}일차 {target_index}번째 장소를 삭제했습니다."

    elif op == ChatOperation.MOVE:
        if target_scope == "DAY_OPTIMIZE":
            if any(_has_missing_coordinate(place) for place in places):
                warnings.append("일부 장소 좌표가 없어 해당 위치는 기존 순서를 유지했습니다.")
                day["places"] = places
                change_summary = (
                    f"{target_day_num}일차 동선 최적화를 시도했지만 일부 장소 좌표가 없어 기존 순서를 유지했습니다."
                )
            else:
                optimized_places = optimize_daily_route(places)
                reorder_visit_sequence(optimized_places)
                day["places"] = optimized_places
                change_summary = (
                    f"{target_day_num}일차의 식사 일정은 유지하고, "
                    "나머지 장소 순서를 이동거리 기준으로 다시 정리했습니다."
                )
            diff_keys.extend(_build_day_diff_keys(day))
        else:
            dest_day_num = intent.get("destination_day", target_day_num)
            dest_index = max(1, intent.get("destination_index", 1))
            dest_pos = dest_index - 1

            if dest_day_num == target_day_num:
                moved = places.pop(target_pos)
                dest_pos = min(dest_pos, len(places))
                places.insert(dest_pos, moved)
                reorder_visit_sequence(places)
                diff_keys.append(build_diff_key(target_day_num, dest_pos + 1))
                change_summary = f"{target_day_num}일차 {target_index}번째 장소를 {dest_pos + 1}번째로 옮겼습니다."
            else:
                dest_day = _find_day(itinerary, dest_day_num)
                if not dest_day:
                    return {**state, "error": f"{dest_day_num}일차를 찾을 수 없습니다."}
                dest_places = dest_day.get("places", [])
                if len(places) <= _MIN_PLACES_PER_DAY:
                    return {
                        **state,
                        "status": ChatStatus.REJECTED,
                        "change_summary": "출발 일차에는 최소 1개 장소가 남아 있어야 합니다.",
                    }
                if len(dest_places) >= _MAX_PLACES_PER_DAY:
                    return {
                        **state,
                        "status": ChatStatus.REJECTED,
                        "change_summary": "도착 일차에는 최대 10개 장소까지만 배치할 수 있습니다.",
                    }
                moved = places.pop(target_pos)
                reorder_visit_sequence(places)
                dest_pos = min(dest_pos, len(dest_places))
                dest_places.insert(dest_pos, moved)
                reorder_visit_sequence(dest_places)
                dest_day["places"] = dest_places
                diff_keys.extend(_build_day_diff_keys(day))
                diff_keys.extend(_build_day_diff_keys(dest_day))
                change_summary = (
                    f"{target_day_num}일차 {target_index}번째 장소를 "
                    f"{dest_day_num}일차 {dest_pos + 1}번째 위치로 옮겼습니다."
                )
    else:
        change_summary = "요청한 수정 작업을 처리했습니다."

    if target_scope not in ("DAY_PLACES", "DAY_OPTIMIZE"):
        day["places"] = places
    diff_keys = _sort_diff_keys(diff_keys)
    diff_str = ",".join(diff_keys)
    append_job_log("mutate", f"op={op} day={target_day_num} idx={target_index} n={len(search_results)} diff={diff_str}")

    return {
        **state,
        "modified_itinerary": itinerary,
        "diff_keys": diff_keys,
        "warnings": warnings,
        "search_results": search_results,
        "change_summary": change_summary,
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
    region_hint = _day_region_hint(day)
    geo_anchored_keyword = f"{region_hint} {keyword}".strip() if region_hint else keyword

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
            bias_results = await service.search(
                keyword,
                min_rating=min_rating,
                location_restriction=None,
                location_bias=day_bbox,
            )
            if bias_results:
                results, filtered_out = _hard_filter_by_bbox(bias_results, day_bbox)
                geo_filtered_out_count += filtered_out

        if not results and day_bbox is not None:
            geo_filter_fallback_unfiltered = True
            unfiltered_results = await service.search(
                geo_anchored_keyword,
                min_rating=min_rating,
                location_restriction=None,
            )
            if unfiltered_results:
                results, filtered_out = _hard_filter_by_bbox(unfiltered_results, day_bbox)
                geo_filtered_out_count += filtered_out
            else:
                results = unfiltered_results

        fallback_to_unfiltered = False
        if not results:
            fallback_to_unfiltered = True
            unfiltered_results = await service.search(
                geo_anchored_keyword,
                min_rating=None,
                location_restriction=None,
            )
            if unfiltered_results and day_bbox is not None:
                results, filtered_out = _hard_filter_by_bbox(unfiltered_results, day_bbox)
                geo_filtered_out_count += filtered_out
            else:
                results = unfiltered_results

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

    append_job_log(
        "mutate_search",
        f"kw={keyword[:40]} bbox={'Y' if day_bbox else 'N'} rerank={rerank_enabled}"
        f" fb_unfilt={fallback_to_unfiltered} n={len(results)}",
        level="detail",
    )

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
