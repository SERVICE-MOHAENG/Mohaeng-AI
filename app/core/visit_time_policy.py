"""visit_time 계산 정책 공용 모듈."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings, get_settings

_SECTION_TIME_MAP = {
    "MORNING": "09:00",
    "LUNCH": "12:00",
    "AFTERNOON": "14:00",
    "DINNER": "18:00",
    "EVENING": "20:00",
    "NIGHT": "22:00",
}

_DEFAULT_START = "09:00"
_DEFAULT_STAY_MINUTES = 90
_DEFAULT_TRANSIT_FACTOR = 15.0
_DEFAULT_TRANSIT_BASE_MINUTES = 10
_DEFAULT_LATE_HOUR = 23
_DEFAULT_WALK_WARNING_MINUTES = 30
_VISIT_TIME_MINUTE_STEP = 30


class VisitTimeOutputMode(StrEnum):
    """visit_time 출력 모드."""

    HHMM = "HHMM"
    SECTION_EN = "SECTION_EN"


@dataclass(slots=True)
class VisitTimePolicyConfig:
    """visit_time 정책 설정."""

    start_minutes: int
    stay_minutes: int
    transit_factor: float
    transit_base_minutes: int
    late_hour: int
    walk_warning_minutes: int = _DEFAULT_WALK_WARNING_MINUTES


def parse_time_to_hhmm_minutes(value: str | None) -> int | None:
    """문자열 시간을 분 단위로 파싱합니다."""
    if not value:
        return None

    text = str(value).strip().upper()
    if not text:
        return None

    is_pm = "PM" in text
    is_am = "AM" in text
    cleaned = text.replace("AM", "").replace("PM", "").strip().rstrip(":")

    parts = cleaned.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError, IndexError):
        return None

    if is_pm and hour != 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


def format_minutes_to_hhmm(total_minutes: int) -> str:
    """분 단위 시간을 HH:MM으로 포맷합니다."""
    normalized = max(0, int(total_minutes))
    hour = (normalized // 60) % 24
    minute = normalized % 60
    return f"{hour:02d}:{minute:02d}"


def format_minutes_to_section_en(total_minutes: int) -> str:
    """분 단위 시간을 섹션 영문 라벨로 변환합니다."""
    hour = (max(0, int(total_minutes)) // 60) % 24
    if hour < 11:
        return "MORNING"
    if hour < 14:
        return "LUNCH"
    if hour < 18:
        return "AFTERNOON"
    if hour < 20:
        return "DINNER"
    if hour < 22:
        return "EVENING"
    return "NIGHT"


def _parse_start_minutes(value: str) -> int:
    parsed = parse_time_to_hhmm_minutes(value)
    if parsed is None:
        parsed = parse_time_to_hhmm_minutes(_DEFAULT_START)
    return parsed if parsed is not None else 540


def _normalize_output_mode(output_mode: VisitTimeOutputMode | str) -> VisitTimeOutputMode:
    if isinstance(output_mode, VisitTimeOutputMode):
        return output_mode
    try:
        return VisitTimeOutputMode(str(output_mode).strip().upper())
    except ValueError:
        return VisitTimeOutputMode.HHMM


def build_visit_time_policy_config(settings: Settings | None = None) -> VisitTimePolicyConfig:
    """설정값으로 visit_time 정책 구성을 만듭니다."""
    resolved_settings = settings or get_settings()
    stay_minutes = max(1, int(resolved_settings.VISIT_TIME_STAY_MINUTES))
    transit_factor = max(0.0, float(resolved_settings.VISIT_TIME_TRANSIT_FACTOR))
    transit_base_minutes = max(0, int(resolved_settings.VISIT_TIME_TRANSIT_BASE_MINUTES))
    late_hour = min(23, max(0, int(resolved_settings.VISIT_TIME_LATE_HOUR)))
    walk_warning_minutes = max(0, int(resolved_settings.VISIT_TIME_WALK_WARNING_MINUTES))

    return VisitTimePolicyConfig(
        start_minutes=_parse_start_minutes(resolved_settings.VISIT_TIME_START),
        stay_minutes=stay_minutes,
        transit_factor=transit_factor,
        transit_base_minutes=transit_base_minutes,
        late_hour=late_hour,
        walk_warning_minutes=walk_warning_minutes,
    )


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calc_transit_minutes(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    transit_factor: float,
    transit_base_minutes: int,
) -> int:
    """두 좌표 간 이동시간(분)을 계산합니다."""
    distance_km = _haversine_distance_km(lat1, lon1, lat2, lon2)
    return int(distance_km * transit_factor + transit_base_minutes)


def _section_minutes(value: str | None) -> int | None:
    key = str(value or "").strip().upper()
    if key in _SECTION_TIME_MAP:
        return parse_time_to_hhmm_minutes(_SECTION_TIME_MAP[key])
    return None


def _resolve_anchor_minutes(place: dict, llm_minutes: int | None) -> int | None:
    if llm_minutes is not None:
        return llm_minutes

    visit_time_value = str(place.get("visit_time") or "")
    parsed_visit_time = parse_time_to_hhmm_minutes(visit_time_value)
    if parsed_visit_time is not None:
        return parsed_visit_time

    section_from_visit_time = _section_minutes(visit_time_value)
    if section_from_visit_time is not None:
        return section_from_visit_time

    section_hint = str(place.get("section") or place.get("section_hint") or "")
    return _section_minutes(section_hint)


def _format_visit_time(total_minutes: int, output_mode: VisitTimeOutputMode) -> str:
    if output_mode == VisitTimeOutputMode.SECTION_EN:
        return format_minutes_to_section_en(total_minutes)
    return format_minutes_to_hhmm(total_minutes)


def _ceil_minutes_to_step(total_minutes: int, step_minutes: int = _VISIT_TIME_MINUTE_STEP) -> int:
    normalized = max(0, int(total_minutes))
    step = max(1, int(step_minutes))
    remainder = normalized % step
    if remainder == 0:
        return normalized
    return normalized + (step - remainder)


def apply_visit_time_policy(
    places: list[dict],
    *,
    day_number: int | None = None,
    config: VisitTimePolicyConfig | None = None,
    llm_proposals_by_sequence: dict[int, str] | None = None,
    output_mode: VisitTimeOutputMode | str = VisitTimeOutputMode.HHMM,
) -> tuple[list[dict], list[str]]:
    """점화식 기반 visit_time 정책을 적용합니다."""
    if not places:
        return places, []

    resolved_config = config or build_visit_time_policy_config()
    resolved_output_mode = _normalize_output_mode(output_mode)
    warnings: list[str] = []
    assigned_minutes: list[int] = []
    day_prefix = f"{day_number}일차" if day_number is not None else "해당 일차"
    proposals = llm_proposals_by_sequence or {}

    for index, place in enumerate(places):
        if index == 0:
            base_time = resolved_config.start_minutes
        else:
            prev_place = places[index - 1]
            prev_assigned = assigned_minutes[-1]
            transit_minutes = 0

            lat1 = prev_place.get("latitude")
            lon1 = prev_place.get("longitude")
            lat2 = place.get("latitude")
            lon2 = place.get("longitude")

            if all(v is not None for v in (lat1, lon1, lat2, lon2)):
                transit_minutes = calc_transit_minutes(
                    float(lat1),
                    float(lon1),
                    float(lat2),
                    float(lon2),
                    resolved_config.transit_factor,
                    resolved_config.transit_base_minutes,
                )
                if transit_minutes > resolved_config.walk_warning_minutes:
                    warnings.append(
                        f"{day_prefix} {prev_place.get('place_name', '')} → "
                        f"{place.get('place_name', '')} 이동 시간이 약 {transit_minutes}분 소요됩니다. "
                        "이동 수단을 변경하시겠어요?"
                    )

            base_time = prev_assigned + resolved_config.stay_minutes + transit_minutes

        sequence_raw = place.get("visit_sequence")
        try:
            sequence = int(sequence_raw)
        except (TypeError, ValueError):
            sequence = index + 1

        proposal_text = proposals.get(sequence, "")
        proposal_minutes = parse_time_to_hhmm_minutes(proposal_text) if proposal_text else None
        anchor_time = _resolve_anchor_minutes(place, proposal_minutes)
        assigned_time = max(base_time, anchor_time) if anchor_time is not None else base_time
        assigned_time = _ceil_minutes_to_step(assigned_time)

        if assigned_time >= 1440:
            warnings.append(f"{day_prefix} 일정이 자정을 초과합니다.")
            for remaining in places[index:]:
                remaining["visit_time"] = "일정 초과"
                remaining.pop("section", None)
                remaining.pop("section_hint", None)
            return places, warnings

        place["visit_time"] = _format_visit_time(assigned_time, resolved_output_mode)
        place.pop("section", None)
        place.pop("section_hint", None)

        if assigned_time // 60 >= resolved_config.late_hour:
            warnings.append(f"{day_prefix} {place.get('place_name', '')} 방문 시각이 {assigned_time // 60}시입니다.")

        assigned_minutes.append(assigned_time)

    return places, warnings
