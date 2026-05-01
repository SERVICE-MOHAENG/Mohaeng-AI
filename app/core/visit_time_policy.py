"""visit_time 계산 정책 공용 모듈."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings, get_settings

_DEFAULT_START = "09:00"
_MIN_VISIT_TIME_MINUTES = 8 * 60
_MAX_VISIT_TIME_MINUTES = 24 * 60
_FALLBACK_END_MINUTES = 24 * 60
_HHMM_PATTERN = re.compile(r"^(?P<hour>\d{2}):(?P<minute>\d{2})$")


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

    if hour == 24 and minute == 0:
        return _MAX_VISIT_TIME_MINUTES

    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


def format_minutes_to_hhmm(total_minutes: int) -> str:
    """분 단위 시간을 HH:MM으로 포맷합니다."""
    normalized = max(0, min(int(total_minutes), _MAX_VISIT_TIME_MINUTES))
    if normalized == _MAX_VISIT_TIME_MINUTES:
        return "24:00"
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


def _is_hhmm_24h(value: str) -> bool:
    match = _HHMM_PATTERN.match(value)
    if not match:
        return False

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour == 24:
        return minute == 0
    return 0 <= hour < 24 and 0 <= minute < 60


def _parse_valid_visit_time(value: str | None) -> int | None:
    if value is None:
        return None

    text = str(value).strip()
    if not _is_hhmm_24h(text):
        return None

    parsed = parse_time_to_hhmm_minutes(text)
    if parsed is None:
        return None
    if not (_MIN_VISIT_TIME_MINUTES <= parsed <= _MAX_VISIT_TIME_MINUTES):
        return None
    return parsed


def apply_visit_time_policy(
    places: list[dict],
    *,
    day_number: int | None = None,
    config: VisitTimePolicyConfig | None = None,
    llm_proposals_by_sequence: dict[int, str] | None = None,
    output_mode: VisitTimeOutputMode | str = VisitTimeOutputMode.HHMM,
) -> tuple[list[dict], list[str]]:
    """LLM 제안을 검증해 visit_time을 결정하고 실패 구간은 안전하게 보정합니다."""
    if not places:
        return places, []

    resolved_config = config or build_visit_time_policy_config()
    resolved_output_mode = _normalize_output_mode(output_mode)
    proposals_provided = llm_proposals_by_sequence is not None
    proposals = llm_proposals_by_sequence or {}
    warnings: list[str] = []
    previous_minutes: int | None = None
    total_count = len(places)

    for index, place in enumerate(places):
        sequence_raw = place.get("visit_sequence")
        try:
            sequence = int(sequence_raw)
        except (TypeError, ValueError):
            sequence = index + 1

        assigned_time: int | None = None
        if proposals_provided:
            proposed_time = proposals.get(sequence)
            proposed_minutes = _parse_valid_visit_time(proposed_time)
            if proposed_time and proposed_minutes is None:
                warnings.append(
                    f"day={day_number} sequence={sequence} invalid_visit_time={proposed_time!r}; fallback applied"
                )
            elif proposed_minutes is not None and previous_minutes is not None and proposed_minutes < previous_minutes:
                warnings.append(
                    f"day={day_number} sequence={sequence} decreasing_visit_time={proposed_time!r}; fallback applied"
                )
            else:
                assigned_time = proposed_minutes

            if assigned_time is None and sequence not in proposals:
                warnings.append(f"day={day_number} sequence={sequence} missing_visit_time; fallback applied")

        if assigned_time is None:
            # 산술적 배분 대신 시작 시각 또는 이전 시각 유지 (최후의 보루)
            assigned_time = previous_minutes if previous_minutes is not None else resolved_config.start_minutes

        if previous_minutes is not None and assigned_time < previous_minutes:
            assigned_time = previous_minutes

        place["visit_time"] = _format_visit_time(assigned_time, resolved_output_mode)
        place.pop("section", None)
        place.pop("section_hint", None)
        previous_minutes = assigned_time

    return places, warnings
