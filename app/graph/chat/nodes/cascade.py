"""당일 타임라인 연쇄 업데이트 및 제약조건 검증 노드."""

from __future__ import annotations

from app.core.logger import get_logger
from app.core.visit_time_policy import (
    VisitTimeOutputMode,
    apply_visit_time_policy,
    build_visit_time_policy_config,
)
from app.graph.chat.state import ChatState
from app.schemas.chat import ChatRoadmap
from app.schemas.enums import ChatStatus, PlanningPreference

logger = get_logger(__name__)


def _extract_modified_days(diff_keys: list[str]) -> set[int]:
    """diff_keys에서 수정된 day_number 집합을 추출합니다."""
    days: set[int] = set()
    for key in diff_keys:
        parts = key.split("_")
        if parts and parts[0].startswith("day"):
            try:
                days.add(int(parts[0][3:]))
            except ValueError:
                continue
    return days


def _resolve_output_mode(itinerary: dict) -> VisitTimeOutputMode:
    raw_preference = itinerary.get("planning_preference")
    preference = PlanningPreference(raw_preference)
    if preference == PlanningPreference.PLANNED:
        return VisitTimeOutputMode.HHMM
    return VisitTimeOutputMode.SECTION_EN


def cascade(state: ChatState) -> ChatState:
    """수정된 Day의 타임라인을 재계산하고 제약조건을 검증합니다."""
    itinerary = state.get("modified_itinerary")
    diff_keys = state.get("diff_keys", [])

    if not itinerary:
        return {**state, "error": "cascade에는 modified_itinerary가 필요합니다."}

    try:
        output_mode = _resolve_output_mode(itinerary)
    except Exception:
        return {
            **state,
            "status": ChatStatus.REJECTED,
            "error": "current_itinerary.planning_preference가 유효하지 않습니다.",
        }

    modified_days = _extract_modified_days(diff_keys)
    visit_time_proposals = state.get("visit_time_proposals", {})
    warnings: list[str] = list(state.get("warnings", []))
    policy_config = build_visit_time_policy_config()

    for day in itinerary.get("itinerary", []):
        day_num = day.get("day_number")
        if day_num not in modified_days:
            continue

        places = day.get("places", [])
        if not places:
            continue

        resolved_places, new_warnings = apply_visit_time_policy(
            places,
            day_number=day_num,
            config=policy_config,
            llm_proposals_by_sequence=visit_time_proposals.get(day_num, {}),
            output_mode=output_mode,
        )
        day["places"] = resolved_places
        warnings.extend(new_warnings)

    try:
        ChatRoadmap.model_validate(itinerary)
    except Exception as exc:
        logger.error("수정된 로드맵 스키마 검증 실패: %s", exc)
        return {
            **state,
            "status": ChatStatus.REJECTED,
            "error": "수정된 로드맵이 스키마 검증에 실패했습니다.",
            "warnings": warnings,
        }

    return {**state, "modified_itinerary": itinerary, "warnings": warnings}
