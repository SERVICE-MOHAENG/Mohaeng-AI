"""수정된 일차의 visit_time 제안 생성 노드."""

from __future__ import annotations

from app.core.visit_time_llm import propose_visit_times_for_days
from app.graph.chat.state import ChatState


def _extract_modified_days(diff_keys: list[str]) -> set[int]:
    days: set[int] = set()
    for key in diff_keys:
        parts = key.split("_")
        if parts and parts[0].startswith("day"):
            try:
                days.add(int(parts[0][3:]))
            except ValueError:
                continue
    return days


async def propose_visit_time(state: ChatState) -> ChatState:
    """수정된 일차만 대상으로 visit_time 제안을 생성합니다."""
    itinerary = state.get("modified_itinerary")
    if not itinerary:
        return {**state, "error": "propose_visit_time에는 modified_itinerary가 필요합니다."}

    modified_days = _extract_modified_days(state.get("diff_keys", []))
    if not modified_days:
        return {**state, "visit_time_proposals": {}}

    target_days: list[dict] = []
    for day in itinerary.get("itinerary", []):
        day_number = day.get("day_number")
        if day_number in modified_days:
            target_days.append({"day_number": day_number, "places": day.get("places", [])})

    proposals = await propose_visit_times_for_days(target_days)
    return {**state, "visit_time_proposals": proposals}
