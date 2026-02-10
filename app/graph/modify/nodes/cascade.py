"""당일 타임라인 연쇄 업데이트 및 제약조건 검증 노드."""

from __future__ import annotations

from app.core.logger import get_logger
from app.graph.modify.state import ModifyState
from app.graph.modify.utils import haversine_distance

logger = get_logger(__name__)

_DEFAULT_STAY_MINUTES = 90
_WALK_WARNING_MINUTES = 30
_LATE_HOUR = 23
_START_HOUR = 9
_START_MINUTE = 0


def _parse_time(visit_time: str) -> tuple[int, int] | None:
    """visit_time 문자열에서 (hour, minute)을 추출합니다."""
    text = visit_time.strip().upper()
    if not text:
        return None

    is_pm = "PM" in text
    is_am = "AM" in text
    cleaned = text.replace("AM", "").replace("PM", "").strip().rstrip(":")

    parts = cleaned.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None

    if is_pm and hour != 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    return hour, minute


def _format_time(hour: int, minute: int) -> str:
    """(hour, minute)을 'HH:MM' 형식으로 변환합니다."""
    return f"{hour:02d}:{minute:02d}"


def _calc_transit_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """두 좌표 간 이동 시간(분)을 계산합니다. 공식: 직선거리(km) × 15 + 10."""
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    return int(dist * 15 + 10)


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


def cascade(state: ModifyState) -> ModifyState:
    """수정된 Day의 타임라인을 재계산하고 제약조건을 검증합니다."""
    itinerary = state.get("modified_itinerary")
    diff_keys = state.get("diff_keys", [])

    if not itinerary:
        return {**state, "error": "cascade에는 modified_itinerary가 필요합니다."}

    modified_days = _extract_modified_days(diff_keys)
    if not modified_days:
        return state

    warnings: list[str] = list(state.get("warnings", []))

    for day in itinerary.get("itinerary", []):
        day_num = day.get("day_number")
        if day_num not in modified_days:
            continue

        places = day.get("places", [])
        if not places:
            continue

        current_hour, current_minute = _START_HOUR, _START_MINUTE

        first_time = _parse_time(places[0].get("visit_time", ""))
        if first_time:
            current_hour, current_minute = first_time

        for i, place in enumerate(places):
            place["visit_time"] = _format_time(current_hour, current_minute)

            if current_hour >= _LATE_HOUR:
                warnings.append(f"{day_num}일차 {place.get('place_name', '')} 방문 시각이 {current_hour}시입니다.")

            current_minute += _DEFAULT_STAY_MINUTES
            current_hour += current_minute // 60
            current_minute = current_minute % 60

            if i < len(places) - 1:
                next_place = places[i + 1]
                lat1 = place.get("latitude")
                lon1 = place.get("longitude")
                lat2 = next_place.get("latitude")
                lon2 = next_place.get("longitude")

                if all(v is not None for v in (lat1, lon1, lat2, lon2)):
                    transit = _calc_transit_minutes(lat1, lon1, lat2, lon2)

                    if transit > _WALK_WARNING_MINUTES:
                        warnings.append(
                            f"{day_num}일차 {place.get('place_name', '')} → "
                            f"{next_place.get('place_name', '')} 이동 시간이 약 {transit}분 소요됩니다. "
                            f"이동 수단을 변경하시겠어요?"
                        )

                    current_minute += transit
                    current_hour += current_minute // 60
                    current_minute = current_minute % 60

            if current_hour >= 24:
                warnings.append(f"{day_num}일차 일정이 자정을 초과합니다.")
                break

    return {**state, "modified_itinerary": itinerary, "warnings": warnings}
