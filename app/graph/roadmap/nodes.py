"""로드맵 그래프 노드."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from functools import lru_cache
from typing import Iterable

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logger import get_logger
from app.graph.roadmap.state import RoadmapState
from app.schemas.course import CourseRequest, CourseResponse, PacePreference, RegionDateRange
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
    skeleton_plan = state["skeleton_plan"]
    fetched_places = state["fetched_places"]
    course_request = CourseRequest.model_validate(state["course_request"])

    context_lines = []
    daily_places_for_schema = []

    for day_plan in skeleton_plan:
        day_number = day_plan["day_number"]
        current_date = course_request.start_date + timedelta(days=day_number - 1)
        context_lines.append(f"\nDay {day_number} ({current_date.strftime('%Y-%m-%d')}):")

        day_places = []
        for i, slot in enumerate(day_plan["slots"]):
            slot_key = _build_slot_key(day_number, i)
            places = fetched_places.get(slot_key, [])
            if places:
                # Mock 서비스에서 1개만 반환하므로 첫 번째 항목 사용
                place = places[0]
                context_lines.append(f"- {slot['section']}: {place['name']} (키워드: {slot['keyword']})")
                day_places.append(
                    {
                        "place_name": place["name"],
                        "place_id": place.get("place_id"),
                        "category": slot["keyword"],
                        "visit_sequence": i + 1,
                        "visit_time": slot["section"],
                    }
                )
        daily_places_for_schema.append({"day_number": day_number, "daily_date": current_date, "places": day_places})

    return "\n".join(context_lines), daily_places_for_schema


async def synthesize_final_roadmap(state: RoadmapState) -> RoadmapState:
    """모든 정보를 종합하여 최종 로드맵을 생성한다."""
    if state.get("error"):
        return state

    required_keys = ["skeleton_plan", "fetched_places", "course_request"]
    if not all(key in state for key in required_keys):
        return {**state, "error": "최종 합성을 위한 데이터가 부족합니다."}

    try:
        # 1. LLM에 전달할 컨텍스트 데이터 준비
        itinerary_context, daily_places = _prepare_final_context(state)
        course_request = state["course_request"]

        # 2. LLM 출력 파서 설정
        parser = PydanticOutputParser(pydantic_object=CourseResponse)

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
            "## 최종 로드맵 생성 가이드\n"
            "1. 위의 '확정된 일자별 장소 목록'을 `itinerary` 필드의 JSON 구조에 맞게 그대로 변환하여 채워주세요. "
            "(`places` 목록은 제공된 데이터를 사용해야 합니다.)\n"
            "2. '원본 사용자 요청'을 참고하여, 이 여행 전체를 아우르는 창의적이고 매력적인 `title`을 생성해주세요.\n"
            "3. '원본 사용자 요청'과 '확정된 장소 목록'을 모두 고려하여, 왜 이 코스가 사용자에게 최고의 선택인지 "
            "설득력 있게 설명하는 `llm_commentary`를 작성해주세요. (2-3문장)\n"
            "4. 사용자가 이 여행 계획을 받은 후 할 수 있는 다음 행동을 `next_action_suggestion`에 간단히 제안해주세요. "
            "(예: '숙소 예약하기', '항공권 알아보기' 등)\n\n"
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

        # 5. 응답 파싱 및 상태 저장
        # 파서가 DailyItinerary의 places를 직접 생성하지 않으므로, LLM 응답에 수동으로 주입
        parsed_data = parser.parse(content).model_dump()
        parsed_data["itinerary"] = daily_places

        return {**state, "final_roadmap": parsed_data}

    except Exception as e:
        logger.error(f"최종 로드맵 생성 실패: {e}", exc_info=True)
        return {**state, "error": f"최종 로드맵 생성에 실패했습니다: {e}"}
