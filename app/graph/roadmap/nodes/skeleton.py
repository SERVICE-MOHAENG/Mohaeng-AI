"""로드맵 스켈레톤 생성 노드."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm_router import Stage, invoke
from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import strip_code_fence
from app.schemas.course import CourseRequest, PacePreference, RegionDateRange
from app.schemas.skeleton import SkeletonPlan

logger = get_logger(__name__)

_ALLOWED_SECTIONS = ("MORNING", "LUNCH", "AFTERNOON", "DINNER", "EVENING", "NIGHT")
_SECTION_TEMPLATES: dict[int, list[str]] = {
    4: ["MORNING", "LUNCH", "AFTERNOON", "DINNER"],
    5: ["MORNING", "LUNCH", "AFTERNOON", "DINNER", "EVENING"],
    6: ["MORNING", "LUNCH", "AFTERNOON", "DINNER", "EVENING", "NIGHT"],
    7: ["MORNING", "MORNING", "LUNCH", "AFTERNOON", "DINNER", "EVENING", "NIGHT"],
}
_SECTION_KEYWORD_DEFAULTS = {
    "MORNING": "대표 명소 도보 탐방",
    "LUNCH": "현지 인기 점심 식사",
    "AFTERNOON": "문화 전시 체험 활동",
    "DINNER": "현지 인기 저녁 식사",
    "EVENING": "야경 명소 산책 코스",
    "NIGHT": "야간 감성 명소 탐방",
}
_GENERIC_KEYWORDS = {
    "맛집",
    "식당",
    "카페",
    "쇼핑",
    "관광",
    "산책",
    "전시",
    "체험",
    "museum",
    "restaurant",
    "cafe",
    "shopping",
    "walk",
}
_MIN_KEYWORD_LENGTH = 8
_MAX_KEYWORD_LENGTH = 40
_MAX_AREA_LENGTH = 40
_COORDINATE_PATTERN = re.compile(r"\b-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+\b")
_PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s\-]{7,}\d)")
_POBOX_PATTERN = re.compile(r"\b(?:p\.?\s*o\.?\s*box|c\/o)\b", flags=re.IGNORECASE)
_ADDRESS_DETAIL_PATTERN = re.compile(
    r"(?:\d+(?:-\d+)?\s*(?:번지|호|동|로|길)\b|\b(?:street|st|road|rd|avenue|ave)\b)",
    flags=re.IGNORECASE,
)
_DIGIT_PATTERN = re.compile(r"\d")


def _slot_range(pace_preference: PacePreference | str | None) -> tuple[int, int]:
    value = pace_preference.value if isinstance(pace_preference, PacePreference) else str(pace_preference or "")
    if value == PacePreference.DENSE:
        return 6, 7
    if value == PacePreference.RELAXED:
        return 4, 5
    return 5, 6


def _join_values(values: Iterable) -> str:
    return ", ".join([str(value) for value in values]) if values else "none"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        value = _normalize_text(item)
        if not value or value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _looks_like_coordinates(text: str) -> bool:
    return bool(_COORDINATE_PATTERN.search(text))


def _looks_like_phone(text: str) -> bool:
    digits = _DIGIT_PATTERN.findall(text)
    if len(digits) < 8:
        return False
    return bool(_PHONE_PATTERN.search(text))


def _contains_po_box_or_care_of(text: str) -> bool:
    return bool(_POBOX_PATTERN.search(text))


def _digit_ratio(text: str) -> float:
    compact = "".join(text.split())
    if not compact:
        return 0.0
    return len(_DIGIT_PATTERN.findall(compact)) / len(compact)


def _looks_like_detail_address(text: str) -> bool:
    if not text:
        return False
    if _ADDRESS_DETAIL_PATTERN.search(text):
        return True
    return _digit_ratio(text) >= 0.25


def _is_search_unfriendly(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return (
        _looks_like_coordinates(normalized) or _looks_like_phone(normalized) or _contains_po_box_or_care_of(normalized)
    )


def _normalized_keyword_for_quality(keyword: str) -> str:
    return _normalize_text(keyword).lower().replace(" ", "")


def _is_keyword_too_generic(keyword: str) -> bool:
    normalized = _normalized_keyword_for_quality(keyword)
    return normalized in _GENERIC_KEYWORDS


def _is_keyword_too_short(keyword: str) -> bool:
    return len(_normalize_text(keyword)) < _MIN_KEYWORD_LENGTH


def _build_slot_targets(segment_days: int, slot_min: int, slot_max: int) -> list[int]:
    if segment_days <= 0:
        return []
    if slot_min >= slot_max:
        return [slot_min] * segment_days
    if segment_days == 1:
        return [slot_min]
    if segment_days == 2:
        return [slot_max, slot_min]
    targets = [slot_min] * segment_days
    if segment_days > 2:
        for index in range(1, segment_days - 1):
            targets[index] = slot_max
    return targets


def _format_slot_targets(slot_targets: list[int]) -> str:
    if not slot_targets:
        return "none"
    return ", ".join([f"Day{index + 1}={count}" for index, count in enumerate(slot_targets)])


def _validate_plan(
    plan: SkeletonPlan,
    total_days: int,
    slot_min: int,
    slot_max: int,
    expected_region: str,
    slot_targets: list[int] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if len(plan.days) != total_days:
        errors.append(f"여행 일수는 {total_days}일이어야 하지만 {len(plan.days)}일로 생성되었습니다.")

    expected_days = set(range(1, total_days + 1))
    actual_days = {day.day_number for day in plan.days}
    if actual_days != expected_days:
        errors.append("day_number는 1부터 연속되는 숫자여야 합니다.")

    for day in plan.days:
        if str(day.region) != str(expected_region):
            errors.append(f"{day.day_number}일차 region은 {expected_region}여야 하지만 {day.region}입니다.")

        slot_count = len(day.slots)
        if slot_targets and 0 < day.day_number <= len(slot_targets):
            target_count = slot_targets[day.day_number - 1]
            if slot_count != target_count:
                errors.append(f"{day.day_number}일차 슬롯 수는 {target_count}개여야 합니다.")
        if slot_count < slot_min or slot_count > slot_max:
            errors.append(f"{day.day_number}일차 슬롯 수가 {slot_count}개입니다 (허용 범위: {slot_min}-{slot_max}).")

        seen_slots: set[tuple[str, str, str]] = set()
        for slot_index, slot in enumerate(day.slots, start=1):
            section = _normalize_text(slot.section).upper()
            area = _normalize_text(slot.area)
            keyword = _normalize_text(slot.keyword)

            if section not in _ALLOWED_SECTIONS:
                errors.append(f"{day.day_number}일차 {slot_index}번 슬롯 section({section})은 허용값이 아닙니다.")
            if not area:
                errors.append(f"{day.day_number}일차 {slot_index}번 슬롯 area가 비어 있습니다.")
            if not keyword:
                errors.append(f"{day.day_number}일차 {slot_index}번 슬롯 keyword가 비어 있습니다.")
            if keyword and _is_keyword_too_short(keyword):
                errors.append(
                    (
                        f"{day.day_number}일차 {slot_index}번 슬롯 keyword가 너무 짧습니다. "
                        f"({_MIN_KEYWORD_LENGTH}자 이상 필요)"
                    )
                )
            if keyword and _is_keyword_too_generic(keyword):
                errors.append(
                    f"{day.day_number}일차 {slot_index}번 슬롯 keyword가 너무 포괄적입니다. 구체화가 필요합니다."
                )
            if len(keyword) > _MAX_KEYWORD_LENGTH:
                errors.append(
                    f"{day.day_number}일차 {slot_index}번 슬롯 keyword 길이가 {_MAX_KEYWORD_LENGTH}자를 초과합니다."
                )
            if _is_search_unfriendly(area) or _is_search_unfriendly(keyword):
                errors.append(
                    (
                        f"{day.day_number}일차 {slot_index}번 슬롯에 "
                        "검색 불리 패턴(좌표/전화번호/P.O.Box/C/O)이 포함되어 있습니다."
                    )
                )
            if _looks_like_detail_address(area):
                errors.append(f"{day.day_number}일차 {slot_index}번 슬롯 area가 상세 주소 형태라 검색 품질이 낮습니다.")

            dedupe_key = (section.lower(), area.lower(), keyword.lower())
            if dedupe_key in seen_slots:
                errors.append(
                    f"{day.day_number}일차 {slot_index}번 슬롯이 동일 슬롯(area+keyword+section)과 중복됩니다."
                )
            else:
                seen_slots.add(dedupe_key)

    return errors, warnings


def _area_warnings(plan: SkeletonPlan) -> list[str]:
    warnings: list[str] = []
    for day in plan.days:
        areas = {slot.area.strip().lower() for slot in day.slots if slot.area}
        if len(areas) > 3:
            warnings.append(f"{day.day_number}일차에 서로 다른 지역이 {len(areas)}개입니다. 이동 동선을 고려하세요.")
    return warnings


def _normalize_region_ranges(
    regions: list[RegionDateRange],
    start_date: date,
    end_date: date,
) -> tuple[list[RegionDateRange], list[str]]:
    errors: list[str] = []

    if not regions:
        return [], ["regions가 비어 있습니다."]

    sorted_regions = sorted(regions, key=lambda item: item.start_date)

    current = start_date
    for segment in sorted_regions:
        if segment.start_date > current:
            errors.append(f"지역 구간 사이에 빈 날짜가 있습니다: {current}부터 {segment.start_date} 이전까지 공백")
        if segment.start_date < current:
            errors.append(f"지역 구간이 겹칩니다: {segment.region} 시작일 {segment.start_date}")
        current = segment.end_date + timedelta(days=1)

    if current != end_date + timedelta(days=1):
        errors.append("지역 구간이 전체 여행 기간과 맞지 않습니다.")

    return sorted_regions, errors


def _build_segment_prompt(
    request: CourseRequest,
    segment: RegionDateRange,
    segment_days: int,
    slot_min: int,
    slot_max: int,
    slot_targets: list[int],
    parser: PydanticOutputParser,
) -> list:
    slot_targets_text = _format_slot_targets(slot_targets)
    system_prompt = (
        "당신은 검색을 위한 여행 일정 스켈레톤을 설계하는 전문 여행 플래너입니다.\n"
        "제약 조건:\n"
        "- 특정 상호명 브랜드는 출력하지 마세요\n"
        "- 각 슬롯은 반드시 Area + Keyword 형식이어야 합니다 "
        "Area는 동네/구역명 Keyword는 활동 또는 장소 유형입니다\n"
        "밀접한 지역이 없다면 오전/오후를 구분해 인접 지역으로 묶습니다\n"
        "- 각 day는 {slot_min}~{slot_max}개의 슬롯을 포함해야 합니다\n"
        "- 슬롯 수 배분은 다음과 같아야 합니다: {slot_targets}\n"
        "- day_number는 지역 구간 내에서 1부터 시작해야 합니다\n"
        "- region은 모든 day에서 반드시 '{region}' 값이어야 합니다\n"
        "- 좌표, 전화번호, P.O. Box/C/O, 상세 번지 주소는 area/keyword에 넣지 마세요\n"
        "- keyword는 실제 Text Search textQuery에 직접 사용됩니다\n"
        "- keyword는 8~40자 사이로 작성하고, 한 단어 대신 구체 맥락(활동+대상+분위기)을 포함하세요\n"
        "- 예시: '한강 야경 산책 코스', '로컬 해산물 저녁 식사', '현대미술 전시 관람'\n"
        "- '맛집', '카페', '쇼핑' 같은 단일 범주형 단어만 쓰지 마세요\n"
        "- 출력은 스키마를 정확히 따라야 하며 추가 텍스트는 금지합니다\n"
    ).format(region=segment.region, slot_min=slot_min, slot_max=slot_max, slot_targets=slot_targets_text)

    user_prompt = (
        "여행 정보(지역 구간 기준):\n"
        "- 지역: {region}\n"
        "- 구간 일정: {segment_start} ~ {segment_end} ({segment_days}일)\n"
        "- 전체 일정: {start_date} ~ {end_date}\n"
        "- 인원: {people_count}\n"
        "- 동행자: {companion_type}\n"
        "- 테마: {travel_themes}\n"
        "- 페이스: {pace_preference}\n"
        "- 계획 성향: {planning_preference}\n"
        "- 목적지 성향: {destination_preference}\n"
        "- 활동 성향: {activity_preference}\n"
        "- 우선순위: {priority_preference}\n"
        "- 추가 메모: {notes}\n\n"
        "요구사항:\n"
        "- 정확히 {segment_days}일치 DayPlan을 생성하세요\n"
        "- 각 day의 region 필드는 반드시 '{region}' 값이어야 합니다\n"
        "- 각 day는 반드시 {slot_min}~{slot_max}개의 범위 내에서 슬롯을 포함해야 합니다\n"
        "- 각 day의 슬롯 수는 다음 배분을 정확히 따라야 합니다: {slot_targets}\n"
        "- 각 슬롯은 section, area, keyword를 포함해야 합니다\n"
        "- section은 다음 중 하나여야 합니다 MORNING, LUNCH, AFTERNOON, DINNER, EVENING, NIGHT\n\n"
        "{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])

    return prompt.format_messages(
        region=segment.region,
        segment_start=segment.start_date,
        segment_end=segment.end_date,
        segment_days=segment_days,
        start_date=request.start_date,
        end_date=request.end_date,
        people_count=request.people_count,
        companion_type=request.companion_type,
        travel_themes=_join_values(request.travel_themes),
        pace_preference=request.pace_preference,
        planning_preference=request.planning_preference,
        destination_preference=request.destination_preference,
        activity_preference=request.activity_preference,
        priority_preference=request.priority_preference,
        notes=request.notes or "none",
        slot_min=slot_min,
        slot_max=slot_max,
        slot_targets=slot_targets_text,
        format_instructions=parser.get_format_instructions(),
    )


def _build_repair_prompt(
    request: CourseRequest,
    segment: RegionDateRange,
    segment_days: int,
    slot_min: int,
    slot_max: int,
    slot_targets: list[int],
    parser: PydanticOutputParser,
    invalid_output: str,
    validation_errors: list[str],
) -> list:
    slot_targets_text = _format_slot_targets(slot_targets)
    system_prompt = (
        "당신은 여행 스켈레톤 JSON 복구 전문가입니다.\n"
        "입력으로 주어진 JSON의 형식/제약 위반만 수정하고 의도는 최대한 유지하세요.\n"
        "반드시 JSON만 출력하고, 설명 텍스트는 절대 포함하지 마세요."
    )
    user_prompt = (
        "복구 대상 지역: {region}\n"
        "지역 구간 일수: {segment_days}\n"
        "허용 슬롯 수 범위: {slot_min}~{slot_max}\n"
        "필수 슬롯 분배: {slot_targets}\n"
        "필수 section: MORNING, LUNCH, AFTERNOON, DINNER, EVENING, NIGHT\n"
        "추가 제약: 좌표/전화번호/P.O. Box/C/O/상세 주소 금지, keyword는 8~40자\n"
        "keyword는 Text Search textQuery로 직접 쓰이므로 구체 맥락(활동+대상+분위기)을 포함\n"
        "'맛집/카페/쇼핑' 같은 단일 범주 단어만 사용 금지\n\n"
        "원본 요청 요약:\n"
        "- 전체 일정: {start_date} ~ {end_date}\n"
        "- 인원: {people_count}\n"
        "- 동행자: {companion_type}\n"
        "- 테마: {travel_themes}\n"
        "- 페이스: {pace_preference}\n\n"
        "검증 오류 목록:\n"
        "{validation_errors}\n\n"
        "문제 있는 JSON:\n"
        "{invalid_output}\n\n"
        "{format_instructions}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    return prompt.format_messages(
        region=segment.region,
        segment_days=segment_days,
        slot_min=slot_min,
        slot_max=slot_max,
        slot_targets=slot_targets_text,
        start_date=request.start_date,
        end_date=request.end_date,
        people_count=request.people_count,
        companion_type=request.companion_type,
        travel_themes=_join_values(request.travel_themes),
        pace_preference=request.pace_preference,
        validation_errors="\n".join([f"- {item}" for item in validation_errors]) if validation_errors else "- 없음",
        invalid_output=invalid_output or "{}",
        format_instructions=parser.get_format_instructions(),
    )


def _section_template_for_count(slot_count: int) -> list[str]:
    if slot_count in _SECTION_TEMPLATES:
        return _SECTION_TEMPLATES[slot_count][:]
    if slot_count <= 0:
        return []
    base = list(_ALLOWED_SECTIONS)
    if slot_count <= len(base):
        return base[:slot_count]
    return [base[min(index, len(base) - 1)] for index in range(slot_count)]


def _default_area_for_region(region: Any) -> str:
    normalized = _normalize_text(region).replace("_", " ").strip()
    return normalized if normalized else "중심지"


def _sanitize_area(area: str, fallback_area: str) -> str:
    candidate = _normalize_text(area)
    if not candidate:
        return fallback_area
    if len(candidate) > _MAX_AREA_LENGTH:
        candidate = candidate[:_MAX_AREA_LENGTH].strip()
    if _is_search_unfriendly(candidate) or _looks_like_detail_address(candidate):
        return fallback_area
    return candidate or fallback_area


def _sanitize_keyword(keyword: str, section: str) -> str:
    fallback = _SECTION_KEYWORD_DEFAULTS.get(section, "대표 명소 도보 탐방")
    candidate = _normalize_text(keyword)
    if not candidate:
        return fallback
    if _is_search_unfriendly(candidate):
        return fallback
    if _is_keyword_too_short(candidate):
        return fallback
    if _is_keyword_too_generic(candidate):
        return fallback
    if len(candidate) > _MAX_KEYWORD_LENGTH:
        candidate = candidate[:_MAX_KEYWORD_LENGTH].strip()
    return candidate or fallback


def _invoke_segment_plan(parser: PydanticOutputParser, messages: list) -> tuple[SkeletonPlan, str]:
    response = invoke(Stage.ROADMAP_SKELETON, messages)
    content = strip_code_fence(response.content)
    plan = parser.parse(content)
    return plan, content


def _autofix_plan(
    plan: SkeletonPlan,
    segment_days: int,
    slot_min: int,
    slot_max: int,
    slot_targets: list[int],
    expected_region: Any,
) -> SkeletonPlan:
    region_value = str(expected_region)
    default_area = _default_area_for_region(region_value)

    day_map: dict[int, Any] = {}
    for day in sorted(plan.days, key=lambda item: item.day_number):
        if day.day_number not in day_map:
            day_map[day.day_number] = day

    fixed_days: list[dict[str, Any]] = []
    for day_number in range(1, segment_days + 1):
        source_day = day_map.get(day_number)
        raw_slots: list[dict[str, str]] = []
        if source_day:
            raw_slots = [
                {
                    "section": _normalize_text(slot.section).upper(),
                    "area": _normalize_text(slot.area),
                    "keyword": _normalize_text(slot.keyword),
                }
                for slot in source_day.slots
            ]

        deduped_slots: list[dict[str, str]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for slot in raw_slots:
            dedupe_key = (
                _normalize_text(slot.get("section")).lower(),
                _normalize_text(slot.get("area")).lower(),
                _normalize_text(slot.get("keyword")).lower(),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped_slots.append(slot)

        slot_target = slot_targets[day_number - 1] if 0 <= day_number - 1 < len(slot_targets) else slot_min
        target_count = min(slot_max, max(slot_min, slot_target))
        section_template = _section_template_for_count(target_count)

        valid_areas = [
            _normalize_text(slot.get("area"))
            for slot in deduped_slots
            if _normalize_text(slot.get("area"))
            and not _is_search_unfriendly(_normalize_text(slot.get("area")))
            and not _looks_like_detail_address(_normalize_text(slot.get("area")))
        ]
        if valid_areas:
            dominant_area = Counter(valid_areas).most_common(1)[0][0]
        else:
            dominant_area = default_area

        fixed_slots: list[dict[str, str]] = []
        for index in range(target_count):
            template_section = section_template[index]
            if index < len(deduped_slots):
                source_slot = deduped_slots[index]
            elif deduped_slots:
                source_slot = deduped_slots[-1]
            else:
                source_slot = {}

            fixed_slots.append(
                {
                    "section": template_section,
                    "area": _sanitize_area(source_slot.get("area", ""), dominant_area),
                    "keyword": _sanitize_keyword(source_slot.get("keyword", ""), template_section),
                }
            )

        fixed_days.append(
            {
                "day_number": day_number,
                "region": region_value,
                "slots": fixed_slots,
            }
        )

    return SkeletonPlan.model_validate({"days": fixed_days})


def generate_skeleton(state: RoadmapState) -> RoadmapState:
    """CourseRequest를 기반으로 스켈레톤을 생성합니다."""
    raw_request = state.get("course_request")
    if not raw_request:
        return {**state, "error": "skeleton 생성에는 course_request가 필요합니다."}

    try:
        request = raw_request if isinstance(raw_request, CourseRequest) else CourseRequest.model_validate(raw_request)
    except Exception as exc:
        logger.error("CourseRequest 검증 실패: %s", exc)
        return {**state, "error": "course_request 형식이 올바르지 않습니다."}

    total_days = (request.end_date - request.start_date).days + 1
    if total_days < 1:
        return {**state, "error": "여행 날짜 범위가 올바르지 않습니다."}

    sorted_regions, region_errors = _normalize_region_ranges(
        request.regions,
        request.start_date,
        request.end_date,
    )
    if region_errors:
        return {**state, "error": " ; ".join(region_errors)}

    slot_min, slot_max = _slot_range(request.pace_preference)
    parser = PydanticOutputParser(pydantic_object=SkeletonPlan)

    full_days: list[dict] = []
    warnings: list[str] = []

    for segment in sorted_regions:
        segment_days = (segment.end_date - segment.start_date).days + 1
        slot_targets = _build_slot_targets(segment_days, slot_min, slot_max)

        messages = _build_segment_prompt(
            request=request,
            segment=segment,
            segment_days=segment_days,
            slot_min=slot_min,
            slot_max=slot_max,
            slot_targets=slot_targets,
            parser=parser,
        )

        generation_attempt = 1
        repair_used = False
        autofix_used = False
        plan: SkeletonPlan | None = None
        raw_content = ""
        validation_errors: list[str] = []
        validation_warnings: list[str] = []

        try:
            plan, raw_content = _invoke_segment_plan(parser, messages)
            validation_errors, validation_warnings = _validate_plan(
                plan,
                segment_days,
                slot_min,
                slot_max,
                expected_region=str(segment.region),
                slot_targets=slot_targets,
            )
        except Exception as exc:
            validation_errors = [f"1차 생성/파싱 실패: {exc}"]
            plan = None

        warnings.extend(validation_warnings)
        if plan is not None:
            warnings.extend(_area_warnings(plan))

        if validation_errors:
            generation_attempt = 2
            repair_used = True
            repair_messages = _build_repair_prompt(
                request=request,
                segment=segment,
                segment_days=segment_days,
                slot_min=slot_min,
                slot_max=slot_max,
                slot_targets=slot_targets,
                parser=parser,
                invalid_output=raw_content,
                validation_errors=validation_errors,
            )

            repaired_plan: SkeletonPlan | None = None
            repaired_errors: list[str] = validation_errors
            repaired_warnings: list[str] = []

            try:
                repaired_plan, _ = _invoke_segment_plan(parser, repair_messages)
                repaired_errors, repaired_warnings = _validate_plan(
                    repaired_plan,
                    segment_days,
                    slot_min,
                    slot_max,
                    expected_region=str(segment.region),
                    slot_targets=slot_targets,
                )
            except Exception as exc:
                repaired_errors = [f"2차 생성/파싱 실패: {exc}"]
                repaired_plan = None

            warnings.extend(repaired_warnings)
            if repaired_plan is not None:
                warnings.extend(_area_warnings(repaired_plan))

            if repaired_errors:
                autofix_used = True
                source_plan = repaired_plan or plan
                if source_plan is None:
                    logger.warning("Skeleton 복구 실패: validation_errors=%s", repaired_errors)
                    return {
                        **state,
                        "trip_days": total_days,
                        "slot_min": slot_min,
                        "slot_max": slot_max,
                        "skeleton_warnings": _dedupe_ordered(warnings),
                        "error": "Skeleton 생성/복구에 실패했습니다.",
                    }

                try:
                    fixed_plan = _autofix_plan(
                        source_plan,
                        segment_days=segment_days,
                        slot_min=slot_min,
                        slot_max=slot_max,
                        slot_targets=slot_targets,
                        expected_region=str(segment.region),
                    )
                except Exception as exc:
                    logger.error("Skeleton 자동 보정 실패: %s", exc)
                    return {
                        **state,
                        "skeleton_plan": source_plan.model_dump().get("days", []),
                        "trip_days": total_days,
                        "slot_min": slot_min,
                        "slot_max": slot_max,
                        "skeleton_warnings": _dedupe_ordered(warnings),
                        "error": "Skeleton 자동 보정에 실패했습니다.",
                    }

                fixed_errors, fixed_warnings = _validate_plan(
                    fixed_plan,
                    segment_days,
                    slot_min,
                    slot_max,
                    expected_region=str(segment.region),
                    slot_targets=slot_targets,
                )
                warnings.extend(fixed_warnings)
                warnings.extend(_area_warnings(fixed_plan))

                if fixed_errors:
                    logger.warning("Skeleton 자동 보정 후 검증 실패: %s", fixed_errors)
                    return {
                        **state,
                        "skeleton_plan": fixed_plan.model_dump().get("days", []),
                        "trip_days": total_days,
                        "slot_min": slot_min,
                        "slot_max": slot_max,
                        "skeleton_warnings": _dedupe_ordered(warnings),
                        "error": " ; ".join(fixed_errors),
                    }
                plan = fixed_plan
            else:
                plan = repaired_plan

        logger.info(
            "Skeleton segment generation completed",
            extra={
                "generation_attempt": generation_attempt,
                "repair_used": repair_used,
                "autofix_used": autofix_used,
                "validation_error_count": len(validation_errors),
            },
        )

        if plan is None:
            return {
                **state,
                "trip_days": total_days,
                "slot_min": slot_min,
                "slot_max": slot_max,
                "skeleton_warnings": _dedupe_ordered(warnings),
                "error": "Skeleton 생성 결과가 비어 있습니다.",
            }

        for day in plan.days:
            local_day = day.day_number
            day_date = segment.start_date + timedelta(days=local_day - 1)
            global_day = (day_date - request.start_date).days + 1
            full_days.append(
                {
                    "day_number": global_day,
                    "region": segment.region,
                    "slots": [slot.model_dump() for slot in day.slots],
                }
            )

    full_days.sort(key=lambda item: item["day_number"])

    expected_days = set(range(1, total_days + 1))
    actual_days = {day["day_number"] for day in full_days}
    if actual_days != expected_days:
        return {
            **state,
            "skeleton_plan": full_days,
            "trip_days": total_days,
            "slot_min": slot_min,
            "slot_max": slot_max,
            "skeleton_warnings": _dedupe_ordered(warnings),
            "error": "지역 구간이 전체 일정과 일치하지 않습니다.",
        }

    return {
        **state,
        "skeleton_plan": full_days,
        "trip_days": total_days,
        "slot_min": slot_min,
        "slot_max": slot_max,
        "skeleton_warnings": _dedupe_ordered(warnings),
    }
