"""로드맵 장소 검색 노드."""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_search_query, build_slot_key
from app.services.google_places_service import get_google_places_service
from app.services.places_service import PlacesServiceProtocol

logger = get_logger(__name__)


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

    fetched_places: dict[str, list] = {}

    tasks: list[tuple[str, str]] = []
    for day in skeleton_plan:
        day_number = day.get("day_number", 0)
        slots = day.get("slots", [])
        for slot_index, slot in enumerate(slots):
            slot_key = build_slot_key(day_number, slot_index)
            query = build_search_query(slot)
            if query:
                tasks.append((slot_key, query))
            else:
                fetched_places[slot_key] = []

    async def search_for_slot(slot_key: str, query: str) -> tuple[str, list]:
        try:
            places = await places_service.search(query)
            return slot_key, [place.model_dump() for place in places]
        except Exception as exc:
            logger.warning("슬롯 %s 검색 실패: %s", slot_key, exc)
            return slot_key, []

    results = await asyncio.gather(*[search_for_slot(key, query) for key, query in tasks])

    for slot_key, places in results:
        fetched_places[slot_key] = places

    logger.info("총 %d개 슬롯에서 장소 검색 완료", len(fetched_places))

    return {
        **state,
        "fetched_places": fetched_places,
    }
