"""로드맵 장소 검색 노드."""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_search_query, build_slot_key
from app.schemas.enums import BudgetRange
from app.services.google_places_service import get_google_places_service
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
        except Exception:
            return {**state, "error": "PlacesService가 주입되지 않았습니다."}

    raw_request = state.get("course_request") or {}
    if isinstance(raw_request, dict):
        budget_range = raw_request.get("budget_range")
    else:
        budget_range = getattr(raw_request, "budget_range", None)
    base_price_levels = _map_budget_to_price_levels(budget_range)

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
            places = await places_service.search(query, price_levels=price_levels)
            if price_levels and not places:
                places = await places_service.search(query, price_levels=None)
            return slot_key, [place.model_dump() for place in places]
        except Exception as exc:
            logger.warning("슬롯 %s 검색 실패: %s", slot_key, exc)
            return slot_key, []

    results = await asyncio.gather(*[search_for_slot(key, query, levels) for key, query, levels in tasks])

    for slot_key, places in results:
        fetched_places[slot_key] = places

    logger.info("총 %d개 슬롯에서 장소 검색 완료", len(fetched_places))

    return {
        **state,
        "fetched_places": fetched_places,
    }
