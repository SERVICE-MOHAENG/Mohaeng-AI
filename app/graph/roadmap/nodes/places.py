"""로드맵 장소 검색 노드."""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_search_query, build_slot_key
from app.schemas.enums import BudgetRange
from app.services.google_places_service import get_google_places_service
from app.services.place_rerank_service import select_place_ids_for_day
from app.services.places_service import PlacesServiceProtocol

logger = get_logger(__name__)


_FOOD_KEYWORD_HINTS = (
    "맛집",
    "식당",
    "레스토랑",
    "음식",
    "한식",
    "중식",
    "일식",
    "양식",
    "분식",
    "뷔페",
    "카페",
    "커피",
    "디저트",
    "베이커리",
    "브런치",
    "아이스크림",
    "치킨",
    "피자",
    "버거",
    "스테이크",
    "파스타",
    "라멘",
    "우동",
    "초밥",
    "스시",
    "돈까스",
    "고기",
    "삼겹",
    "갈비",
    "해산물",
    "횟집",
    "bar",
    "pub",
    "izakaya",
    "bbq",
    "bistro",
    "restaurant",
    "cafe",
    "coffee",
    "bakery",
    "dessert",
    "brunch",
)


def _map_budget_to_price_levels(budget_range: str | BudgetRange | None) -> list[str] | None:
    if not budget_range:
        return None
    value = budget_range.value if isinstance(budget_range, BudgetRange) else str(budget_range)
    mapping = {
        BudgetRange.LOW.value: ["PRICE_LEVEL_INEXPENSIVE"],
        BudgetRange.MID.value: ["PRICE_LEVEL_MODERATE"],
        BudgetRange.HIGH.value: ["PRICE_LEVEL_EXPENSIVE"],
        BudgetRange.LUXURY.value: ["PRICE_LEVEL_VERY_EXPENSIVE"],
    }
    return mapping.get(value)


def _is_food_keyword(keyword: str) -> bool:
    normalized = (keyword or "").strip().lower()
    if not normalized:
        return False
    return any(hint in normalized for hint in _FOOD_KEYWORD_HINTS)


def _price_levels_for_slot(slot: dict, base_price_levels: list[str] | None) -> list[str] | None:
    if not base_price_levels:
        return None
    keyword = str(slot.get("keyword") or "").strip()
    if not _is_food_keyword(keyword):
        return None
    return base_price_levels


def _move_selected_first(places: list[dict], selected_place_id: str) -> tuple[list[dict], bool]:
    selected_index = next(
        (index for index, place in enumerate(places) if str(place.get("place_id") or "").strip() == selected_place_id),
        None,
    )
    if selected_index in (None, 0):
        return places, False
    reordered = [places[selected_index], *places[:selected_index], *places[selected_index + 1 :]]
    return reordered, True


async def fetch_places_from_slots(
    state: RoadmapState,
    config: RunnableConfig,
) -> RoadmapState:
    """스켈레톤 슬롯을 기반으로 장소를 검색해 상태에 저장합니다."""
    if state.get("error"):
        return state

    skeleton_plan = state.get("skeleton_plan")
    if not skeleton_plan:
        return {**state, "error": "fetch_places_from_slots에는 skeleton_plan이 필요합니다."}

    places_service: PlacesServiceProtocol | None = config.get("configurable", {}).get("places_service")
    if places_service is None:
        try:
            places_service = get_google_places_service()
        except Exception as exc:
            logger.error("PlacesService 초기화 실패: %s", exc)
            return {**state, "error": "PlacesService가 주입되지 않았습니다."}

    raw_request = state.get("course_request") or {}
    if isinstance(raw_request, dict):
        budget_range = raw_request.get("budget_range")
    else:
        budget_range = getattr(raw_request, "budget_range", None)
    base_price_levels = _map_budget_to_price_levels(budget_range)
    settings = get_settings()
    min_rating = settings.GOOGLE_PLACES_MIN_RATING
    rerank_enabled = settings.GOOGLE_PLACES_LLM_RERANK_ENABLED
    rerank_max_candidates = settings.GOOGLE_PLACES_LLM_RERANK_MAX_CANDIDATES
    rerank_timeout_seconds = get_timeout_policy(settings).llm_timeout_seconds

    fetched_places: dict[str, list] = {}

    tasks: list[tuple[str, str, list[str] | None]] = []
    for day in skeleton_plan:
        day_number = day.get("day_number", 0)
        slots = day.get("slots", [])
        for slot_index, slot in enumerate(slots):
            slot_key = build_slot_key(day_number, slot_index)
            query = build_search_query(slot)
            if query:
                slot_price_levels = _price_levels_for_slot(slot, base_price_levels)
                tasks.append((slot_key, query, slot_price_levels))
            else:
                fetched_places[slot_key] = []

    async def search_for_slot(slot_key: str, query: str, price_levels: list[str] | None) -> tuple[str, list]:
        try:
            places = await places_service.search(query, price_levels=price_levels, min_rating=min_rating)
            if price_levels and not places:
                places = await places_service.search(query, price_levels=None, min_rating=min_rating)
            fallback_to_unfiltered = False
            if not places:
                fallback_to_unfiltered = True
                places = await places_service.search(query, price_levels=None, min_rating=None)

            logger.info(
                "Places search result: slot=%s min_rating_applied=%s fallback_to_unfiltered=%s candidate_count=%d",
                slot_key,
                min_rating is not None,
                fallback_to_unfiltered,
                len(places),
            )
            return slot_key, [place.model_dump() for place in places]
        except Exception as exc:
            logger.warning("슬롯 %s 검색 실패: %s", slot_key, exc)
            return slot_key, []

    results = await asyncio.gather(*[search_for_slot(key, query, levels) for key, query, levels in tasks])

    for slot_key, places in results:
        fetched_places[slot_key] = places

    if rerank_enabled:

        async def rerank_for_day(day: dict) -> None:
            day_number = day.get("day_number", 0)
            slots_payload: list[dict] = []
            for slot_index, slot in enumerate(day.get("slots", [])):
                slot_key = build_slot_key(day_number, slot_index)
                candidates = fetched_places.get(slot_key, [])
                if not candidates:
                    continue
                slots_payload.append(
                    {
                        "slot_key": slot_key,
                        "section": slot.get("section"),
                        "area": slot.get("area"),
                        "keyword": slot.get("keyword"),
                        "candidates": candidates[:rerank_max_candidates],
                    }
                )

            if not slots_payload:
                return

            selected_map = await select_place_ids_for_day(
                day_number=day_number,
                slots=slots_payload,
                max_candidates=rerank_max_candidates,
                timeout_seconds=rerank_timeout_seconds,
            )
            if selected_map is None:
                logger.info(
                    (
                        "Roadmap place rerank result: flow=roadmap day=%s "
                        "batch_size=%d selected=0 missed=%d fallback_used=true"
                    ),
                    day_number,
                    len(slots_payload),
                    len(slots_payload),
                )
                return

            selected_count = 0
            missed_count = 0
            for slot in slots_payload:
                slot_key = slot["slot_key"]
                selected_place_id = selected_map.get(slot_key)
                if not selected_place_id:
                    missed_count += 1
                    continue
                selected_count += 1
                original_places = fetched_places.get(slot_key, [])
                reordered_places, _ = _move_selected_first(original_places, selected_place_id)
                fetched_places[slot_key] = reordered_places

            logger.info(
                (
                    "Roadmap place rerank result: flow=roadmap day=%s "
                    "batch_size=%d selected=%d missed=%d fallback_used=false"
                ),
                day_number,
                len(slots_payload),
                selected_count,
                missed_count,
            )

        await asyncio.gather(*[rerank_for_day(day) for day in skeleton_plan])

    logger.info("총 %d개 슬롯에서 장소 검색 완료", len(fetched_places))

    return {
        **state,
        "fetched_places": fetched_places,
    }
