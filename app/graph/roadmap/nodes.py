"""로드맵 그래프 노드."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from functools import lru_cache
from typing import Iterable

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.schemas.course import (
    CourseRequest,
    CourseResponseLLMOutput,
    PacePreference,
    PlanningPreference,
    RegionDateRange,
)
from app.schemas.skeleton import SkeletonPlan
from app.services.places_service import PlacesServiceProtocol

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


class VisitTimeSlot(BaseModel):
    """방문 순서별 방문 시각 모델."""

    visit_sequence: int = Field(..., ge=1, description="방문 순서")
    visit_time: str = Field(..., description="방문 시각 (HH:MM, 24시간)")


class VisitTimeDay(BaseModel):
    """일자별 방문 시각 모델."""

    day_number: int = Field(..., ge=1, description="여행 일자")
    places: list[VisitTimeSlot] = Field(..., description="방문 시각 목록")


class VisitTimePlan(BaseModel):
    """LLM이 생성한 방문 시각 결과 모델."""

    days: list[VisitTimeDay] = Field(..., description="일자별 방문 시각 결과")


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


def _build_slot_key(day_number: int, slot_index: int) -> str:
    """슬롯의 고유 키를 생성한다."""
    return f"day{day_number}_slot{slot_index}"


def _build_search_query(slot: dict) -> str:
    """슬롯에서 검색 쿼리를 생성한다."""
    area = slot.get("area", "").strip()
    keyword = slot.get("keyword", "").strip()
    return f"{area} {keyword}".strip()


def _get_default_places_service() -> PlacesServiceProtocol:
    """기본 Places 서비스 인스턴스를 반환한다.

    TODO: API Key 발급 후 GooglePlacesService로 교체 예정.
    """
    from tests.mocks.mock_places_service import MockGooglePlacesService

    return MockGooglePlacesService()


async def fetch_places_from_slots(
    state: RoadmapState,
    places_service: PlacesServiceProtocol | None = None,
) -> RoadmapState:
    """skeleton_plan의 각 슬롯에 대해 장소를 검색하여 fetched_places에 저장한다.

    Args:
        state: 현재 로드맵 상태
        places_service: Places 서비스 인스턴스 (의존성 주입). None이면 기본 서비스 사용.

    Returns:
        fetched_places가 추가된 새로운 상태
    """
    # 이전 단계에서 에러가 있으면 중단
    if state.get("error"):
        return state

    skeleton_plan = state.get("skeleton_plan")
    if not skeleton_plan:
        return {**state, "error": "fetch_places_from_slots에는 skeleton_plan이 필요합니다."}

    if places_service is None:
        places_service = _get_default_places_service()

    fetched_places: dict[str, list] = {}

    # 모든 슬롯에 대한 검색 태스크 생성
    tasks: list[tuple[str, str]] = []  # (slot_key, query)
    for day in skeleton_plan:
        day_number = day.get("day_number", 0)
        slots = day.get("slots", [])
        for slot_index, slot in enumerate(slots):
            slot_key = _build_slot_key(day_number, slot_index)
            query = _build_search_query(slot)
            if query:
                tasks.append((slot_key, query))
            else:
                fetched_places[slot_key] = []

    # 비동기 병렬 검색 실행
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


def _prepare_final_context(
    state: RoadmapState,
) -> tuple[str, list[dict]]:
    """LLM에 전달할 최종 컨텍스트 문자열과 일자별 장소 목록을 생성한다."""
    # 1. 입력 데이터 유효성 검증
    skeleton_plan = state.get("skeleton_plan")
    fetched_places = state.get("fetched_places")
    raw_request = state.get("course_request")

    if not skeleton_plan:
        raise ValueError("Context 생성을 위한 `skeleton_plan` 데이터가 없습니다.")
    if not fetched_places:
        raise ValueError("Context 생성을 위한 `fetched_places` 데이터가 없습니다.")
    if not raw_request:
        raise ValueError("Context 생성을 위한 `course_request` 데이터가 없습니다.")

    try:
        course_request = CourseRequest.model_validate(raw_request)
    except Exception as e:
        raise ValueError(f"CourseRequest 모델 유효성 검증에 실패했습니다: {e}") from e

    planning_preference = course_request.planning_preference

    context_lines = []
    daily_places_for_schema = []
    for day_plan in skeleton_plan:
        day_number = day_plan["day_number"]
        current_date = course_request.start_date + timedelta(days=day_number - 1)
        context_lines.append(f"\nDay {day_number} ({current_date.strftime('%Y-%m-%d')}):")

        day_places = []
        visit_sequence_counter = 1  # 일자별 방문 순서 카운터 초기화
        for i, slot in enumerate(day_plan["slots"]):
            slot_key = _build_slot_key(day_number, i)
            places = fetched_places.get(slot_key, [])
            if places:
                # Mock 서비스에서 1개만 반환하므로 첫 번째 항목 사용
                place = places[0]
                context_lines.append(f"- {slot['section']}: {place['name']} (키워드: {slot['keyword']})")

                if planning_preference == PlanningPreference.PLANNED:
                    visit_time = None
                else:
                    visit_time = slot["section"]
                geometry = place.get("geometry") or {}
                place_url = place.get("url")
                if not place_url and place.get("place_id"):
                    place_url = f"https://www.google.com/maps/search/?api=1&query={place['name']}&query_place_id={place.get('place_id')}"

                place_payload = {
                    "place_name": place["name"],
                    "place_id": place.get("place_id"),
                    "address": place.get("address"),
                    "latitude": geometry.get("latitude"),
                    "longitude": geometry.get("longitude"),
                    "place_url": place_url,
                    "description": f"{place['name']}에 대한 한 줄 설명입니다.",
                    "visit_sequence": visit_sequence_counter,
                    "visit_time": visit_time,
                }
                if planning_preference == PlanningPreference.PLANNED:
                    place_payload["section"] = slot.get("section")
                day_places.append(place_payload)
                visit_sequence_counter += 1  # 장소가 추가될 때만 카운터 증가

        daily_places_for_schema.append(
            {"day_number": day_number, "daily_date": current_date.isoformat(), "places": day_places}
        )

    return "\n".join(context_lines), daily_places_for_schema


async def _fill_visit_times_with_llm(daily_places: list[dict]) -> list[dict]:
    """LLM을 통해 방문 시각을 채운다."""
    parser = PydanticOutputParser(pydantic_object=VisitTimePlan)
    settings = get_settings()
    timeout_seconds = settings.LLM_TIMEOUT_SECONDS

    section_time_map = {
        "MORNING": "09:00",
        "LUNCH": "12:00",
        "AFTERNOON": "14:00",
        "DINNER": "18:00",
        "EVENING": "20:00",
        "NIGHT": "22:00",
    }

    def _fallback_visit_time(place: dict, index: int) -> str:
        section_hint = place.get("section")
        if section_hint:
            normalized = str(section_hint).strip().upper()
            if normalized in section_time_map:
                return section_time_map[normalized]

        sequence = place.get("visit_sequence")
        try:
            sequence_value = int(sequence)
        except (TypeError, ValueError):
            sequence_value = index + 1

        base_hour = 9 + max(0, sequence_value - 1) * 2
        if base_hour > 23:
            base_hour = 23
        return f"{base_hour:02d}:00"

    def _apply_fallback() -> list[dict]:
        for day in daily_places:
            for index, place in enumerate(day.get("places", [])):
                place["visit_time"] = _fallback_visit_time(place, index)
                place.pop("section", None)
        return daily_places

    input_days = []
    for day in daily_places:
        input_days.append(
            {
                "day_number": day.get("day_number"),
                "daily_date": day.get("daily_date"),
                "places": [
                    {
                        "visit_sequence": place.get("visit_sequence"),
                        "place_name": place.get("place_name"),
                        "section_hint": place.get("section"),
                        "address": place.get("address"),
                        "latitude": place.get("latitude"),
                        "longitude": place.get("longitude"),
                    }
                    for place in day.get("places", [])
                ],
            }
        )

    system_prompt = (
        "당신은 여행 일정의 방문 시각을 계획하는 전문가입니다.\n"
        "먼저 전체 일정을 훑고 내부적으로 추론한 뒤, 각 장소의 방문 시각을 24시간 HH:MM 형식으로 작성하세요.\n"
        "section_hint는 시간대 힌트이며, 실제 시간은 동선과 장소 간 이동을 고려해 자연스럽게 배치하세요.\n"
        "각 날짜의 시작 시간은 09:00이며, visit_sequence 순서를 유지하고 시간은 점진적으로 증가해야 합니다.\n"
        "입력에 없는 장소를 추가하거나 순서를 바꾸지 마세요. 사고 과정은 출력하지 말고 JSON만 반환하세요."
    )
    user_prompt = (
        "아래 장소 목록을 기준으로 방문 시각을 채워주세요.\n"
        "시작 시간: 09:00\n"
        "입력 데이터:\n"
        "{places}\n\n"
        "{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    messages = prompt.format_messages(
        places=json.dumps(input_days, ensure_ascii=False, indent=2),
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = await asyncio.wait_for(get_llm().ainvoke(messages), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error("Visit time LLM timed out after %s seconds", timeout_seconds)
        return _apply_fallback()
    except Exception:
        logger.exception("Visit time LLM call failed")
        return _apply_fallback()

    try:
        content = _strip_code_fence(response.content)
        visit_plan = parser.parse(content)
    except Exception:
        logger.exception("Visit time parse failed")
        return _apply_fallback()

    visit_time_map = {
        (day.day_number, slot.visit_sequence): slot.visit_time for day in visit_plan.days for slot in day.places
    }

    for day in daily_places:
        day_number = day.get("day_number")
        for index, place in enumerate(day.get("places", [])):
            key = (day_number, place.get("visit_sequence"))
            visit_time = visit_time_map.get(key)
            if not visit_time:
                logger.warning(
                    "Missing visit_time for day %s sequence %s; using fallback",
                    day_number,
                    place.get("visit_sequence"),
                )
                visit_time = _fallback_visit_time(place, index)
            place["visit_time"] = visit_time
            place.pop("section", None)

    return daily_places


async def synthesize_final_roadmap(state: RoadmapState) -> RoadmapState:
    """모든 정보를 종합하여 최종 로드맵을 생성한다."""
    if state.get("error"):
        return state

    try:
        # 1. LLM에 전달할 컨텍스트 데이터 준비
        itinerary_context, daily_places = _prepare_final_context(state)
        course_request = CourseRequest.model_validate(state["course_request"])
        if course_request.planning_preference == PlanningPreference.PLANNED:
            daily_places = await _fill_visit_times_with_llm(daily_places)

        # 2. LLM 출력 파서 설정 (itinerary 제외)
        parser = PydanticOutputParser(pydantic_object=CourseResponseLLMOutput)

        # 3. 프롬프트 구성
        system_prompt = (
            "당신은 전문 여행 플래너입니다. 주어진 여행 정보와 확정된 장소 목록을 바탕으로, "
            "사용자를 위한 최종 여행 로드맵을 완성하는 임무를 받았습니다.\n"
            "창의적인 여행 제목과, 왜 이 코스가 사용자에게 좋은지에 대한 설득력 있는 설명을 반드시 포함해야 합니다.\n"
            "출력은 반드시 제공된 JSON 스키마를 엄격하게 따라야 합니다."
        )
        human_prompt_template = (
            "## 원본 사용자 요청\n"
            "{course_request}\n\n"
            "## 확정된 일자별 장소 목록\n"
            "{itinerary_context}\n\n"
            "## 생성 작업 가이드\n"
            "1. '원본 사용자 요청'을 참고하여, 이 여행 전체를 아우르는 창의적이고 매력적인 `title`을 생성해주세요. "
            "(반드시 한국어로 작성하며 10자 이내로 짧게 작성하고, 나라명 또는 도시명을 반드시 포함해주세요)\n"
            "2. 로드맵을 한 줄로 요약한 `summary`를 한국어로 작성해주세요. (1문장)\n"
            "3. 전체 일정을 대표할 수 있는 핵심 키워드 태그 3~5개를 `tags` 필드에 한국어로 생성해주세요.\n"
            "4. '원본 사용자 요청'과 '확정된 장소 목록'을 모두 고려하여, 왜 이 코스가 사용자에게 최고의 선택인지 "
            "설득력 있게 설명하는 `llm_commentary`를 작성해주세요. (2-3문장)\n"
            "5. 사용자가 바로 입력할 수 있는 다음 행동 문장을 `next_action_suggestion`에 JSON 배열로 작성해주세요. "
            "(2~3개, 사용자 요청과 일정 내용을 바탕으로 맞춤형으로 작성하며 아래 예시는 절대 그대로 출력하지 마세요. "
            '예시 형식: "도쿄 시부야 맛집을 넣어서 2일차 일정을 수정해줘.", '
            '"지금 로드맵에서 더 자연친화적으로 만드는 방법은 없어?")\n\n'
            "## 출력 포맷\n"
            "{format_instructions}"
        )

        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt_template)])
        messages = prompt.format_messages(
            course_request=course_request,
            itinerary_context=itinerary_context,
            format_instructions=parser.get_format_instructions(),
        )

        # 4. LLM 호출
        llm = get_llm()
        response = await llm.ainvoke(messages)
        content = _strip_code_fence(response.content)

        # 5. 응답 파싱 및 데이터 조합
        trip_days = state["trip_days"]
        llm_output = parser.parse(content).model_dump()

        final_roadmap = {
            # 여행 메타데이터 추가
            "start_date": course_request.start_date.isoformat(),
            "end_date": course_request.end_date.isoformat(),
            "trip_days": trip_days,
            "nights": trip_days - 1 if trip_days > 0 else 0,
            "people_count": course_request.people_count,
            # LLM 생성 컨텐츠와 조합
            **llm_output,
            "itinerary": daily_places,
        }

        return {**state, "final_roadmap": final_roadmap}

    except Exception as e:
        logger.error(f"최종 로드맵 생성 실패: {e}", exc_info=True)
        return {**state, "error": f"최종 로드맵 생성에 실패했습니다: {e}"}
