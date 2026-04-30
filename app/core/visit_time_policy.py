"""visit_time 계산 정책 공용 모듈."""

from __future__ import annotations

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
_SEQUENCE_TIME_MAP = {
    1: "09:00",
    2: "12:00",
    3: "14:00",
    4: "18:00",
    5: "20:00",
    6: "22:00",
    7: "23:00",
}

_DEFAULT_START = "09:00"


class VisitTimeOutputMode(StrEnum):
    """visit_time 출력 모드."""

    HHMM = "HHMM"
    SECTION_EN = "SECTION_EN"


@dataclass(slots=True)
class VisitTimePolicyConfig:
    """visit_time 정책 설정."""

    start_minutes: int


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

    return VisitTimePolicyConfig(
        start_minutes=_parse_start_minutes(resolved_settings.VISIT_TIME_START),
    )


def _format_visit_time(total_minutes: int, output_mode: VisitTimeOutputMode) -> str:
    if output_mode == VisitTimeOutputMode.SECTION_EN:
        return format_minutes_to_section_en(total_minutes)
    return format_minutes_to_hhmm(total_minutes)


def _sequence_minutes(sequence: int, config: VisitTimePolicyConfig) -> int:
    mapped = _SEQUENCE_TIME_MAP.get(sequence)
    if mapped is not None:
        parsed = parse_time_to_hhmm_minutes(mapped)
        if parsed is not None:
            return parsed

    last_sequence = max(_SEQUENCE_TIME_MAP)
    last_mapped = parse_time_to_hhmm_minutes(_SEQUENCE_TIME_MAP[last_sequence])
    return last_mapped if last_mapped is not None else config.start_minutes


def apply_visit_time_policy(
    places: list[dict],
    *,
    day_number: int | None = None,
    config: VisitTimePolicyConfig | None = None,
    llm_proposals_by_sequence: dict[int, str] | None = None,
    output_mode: VisitTimeOutputMode | str = VisitTimeOutputMode.HHMM,
) -> tuple[list[dict], list[str]]:
    """visit_sequence 기반 고정 visit_time 정책을 적용합니다."""
    if not places:
        return places, []

    resolved_config = config or build_visit_time_policy_config()
    resolved_output_mode = _normalize_output_mode(output_mode)
    _ = day_number, llm_proposals_by_sequence

    for index, place in enumerate(places):
        sequence_raw = place.get("visit_sequence")
        try:
            sequence = int(sequence_raw)
        except (TypeError, ValueError):
            sequence = index + 1

        assigned_time = _sequence_minutes(sequence, resolved_config)
        place["visit_time"] = _format_visit_time(assigned_time, resolved_output_mode)
        place.pop("section", None)
        place.pop("section_hint", None)

    return places, []
