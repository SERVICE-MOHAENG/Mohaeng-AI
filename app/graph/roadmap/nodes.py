"""로드맵 그래프 노드."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Iterable

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.schemas.course import CourseRequest, PacePreference, RegionDateRange
from app.schemas.skeleton import SkeletonPlan

logger = get_logger(__name__)


@lru_cache
def get_llm() -> ChatOpenAI:
    """캐시된 ChatOpenAI 인스턴스를 반환한다."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=get_settings().OPENAI_API_KEY)


def _slot_range(pace_preference: PacePreference | str | None) -> tuple[int, int]:
    value = pace_preference.value if isinstance(pace_preference, PacePreference) else str(pace_preference or "")
    if value == PacePreference.DENSE:
        return 6, 7
    if value == PacePreference.RELAXED:
        return 4, 5
    return 5, 6


def _strip_code_fence(text: str) -> str:
    content = (text or "").strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) > 1:
            content = parts[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
    return content.strip()


def _join_values(values: Iterable) -> str:
    return ", ".join([str(value) for value in values]) if values else "none"


def _validate_plan(plan: SkeletonPlan, total_days: int, slot_min: int, slot_max: int) -> list[str]:
    errors: list[str] = []

    if len(plan.days) != total_days:
        errors.append(f"여행 일수는 {total_days}일이어야 하지만 {len(plan.days)}일로 생성되었습니다.")

    expected_days = set(range(1, total_days + 1))
    actual_days = {day.day_number for day in plan.days}
    if actual_days != expected_days:
        errors.append("day_number는 1부터 연속된 숫자여야 합니다.")

    for day in plan.days:
        slot_count = len(day.slots)
        if slot_count < slot_min or slot_count > slot_max:
            errors.append(f"{day.day_number}일차 슬롯 수가 {slot_count}개입니다 (허용 범위: {slot_min}-{slot_max}).")

    return errors


def _area_warnings(plan: SkeletonPlan) -> list[str]:
    warnings: list[str] = []
    for day in plan.days:
        areas = {slot.area.strip().lower() for slot in day.slots if slot.area}
        if len(areas) > 3:
            warnings.append(f"{day.day_number}일차에 서로 다른 지역이 {len(areas)}개입니다. 클러스터링을 고려하세요.")
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
        errors.append("지역 구간이 전체 여행 기간을 모두 덮지 못합니다.")

    return sorted_regions, errors


def _build_segment_prompt(
    request: CourseRequest,
    segment: RegionDateRange,
    segment_days: int,
    slot_min: int,
    slot_max: int,
    parser: PydanticOutputParser,
) -> list:
    system_prompt = (
        "당신은 검색을 위한 여행 일정 뼈대(Skeleton)를 설계하는 전문 여행 플래너입니다.\n"
        "제약 조건:\n"
        "- 특정 상호명/브랜드명은 절대 출력하지 마세요.\n"
        "- 각 슬롯은 반드시 Area + Keyword 형식이어야 합니다. "
        "Area는 동네/구역명, Keyword는 활동 또는 장소 유형입니다.\n"
        "- 이동 시간을 줄이기 위해 하루 내 지역을 클러스터링하세요. "
        "특별한 지시가 없다면 오전/오후는 같은 지역 또는 인접 지역으로 묶습니다.\n"
        "- day_number는 이 지역 구간 내에서 1부터 시작해야 합니다.\n"
        "- region은 모든 day에 대해 반드시 '{region}' 값으로 고정해 주세요.\n"
        "- 출력은 스키마를 정확히 따라야 하며, 추가 텍스트는 금지합니다.\n"
    ).format(region=segment.region)

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
        "- 예산: {budget_range}\n"
        "- 추가 메모: {notes}\n\n"
        "요구사항:\n"
        "- 정확히 {segment_days}일치의 DayPlan을 생성하세요.\n"
        "- 각 day는 region 필드를 포함해야 하며 값은 '{region}'이어야 합니다.\n"
        "- 각 day는 {slot_min}~{slot_max}개의 슬롯을 포함해야 합니다.\n"
        "- 각 슬롯은 section, area, keyword를 포함해야 합니다.\n"
        "- section은 다음 중 하나여야 합니다: MORNING, LUNCH, AFTERNOON, DINNER, EVENING, NIGHT.\n\n"
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
        budget_range=request.budget_range,
        notes=request.notes or "none",
        slot_min=slot_min,
        slot_max=slot_max,
        format_instructions=parser.get_format_instructions(),
    )


def generate_skeleton(state: RoadmapState) -> RoadmapState:
    """CourseRequest를 기반으로 여행 뼈대(Skeleton)를 생성한다."""
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

        messages = _build_segment_prompt(
            request=request,
            segment=segment,
            segment_days=segment_days,
            slot_min=slot_min,
            slot_max=slot_max,
            parser=parser,
        )

        try:
            response = get_llm().invoke(messages)
            content = _strip_code_fence(response.content)
            plan = parser.parse(content)
        except Exception as exc:
            logger.error("Skeleton 생성 실패: %s", exc)
            return {**state, "error": "Skeleton 생성에 실패했습니다."}

        validation_errors = _validate_plan(plan, segment_days, slot_min, slot_max)
        warnings.extend(_area_warnings(plan))
        if validation_errors:
            logger.warning("Skeleton 검증 실패: %s", validation_errors)
            return {
                **state,
                "skeleton_plan": plan.model_dump().get("days", []),
                "trip_days": total_days,
                "slot_min": slot_min,
                "slot_max": slot_max,
                "skeleton_warnings": warnings,
                "error": " ; ".join(validation_errors),
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
            "skeleton_warnings": warnings,
            "error": "지역 구간이 전체 일정과 일치하지 않습니다.",
        }

    return {
        **state,
        "skeleton_plan": full_days,
        "trip_days": total_days,
        "slot_min": slot_min,
        "slot_max": slot_max,
        "skeleton_warnings": warnings,
    }
