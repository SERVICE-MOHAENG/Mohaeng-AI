"""로드맵 최종 합성 노드."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logger import get_logger
from app.graph.roadmap.llm import get_llm
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_slot_key, strip_code_fence
from app.schemas.course import CourseRequest, CourseResponseLLMOutput, PlanningPreference

logger = get_logger(__name__)


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


def _prepare_final_context(
    state: RoadmapState,
) -> tuple[str, list[dict]]:
    """LLM 입력 컨텍스트와 일자별 장소 목록을 생성합니다."""
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
    except Exception as exc:
        raise ValueError(f"CourseRequest 모델 유효성 검증에 실패했습니다: {exc}") from exc

    planning_preference = course_request.planning_preference

    context_lines = []
    daily_places_for_schema = []
    for day_plan in skeleton_plan:
        day_number = day_plan["day_number"]
        current_date = course_request.start_date + timedelta(days=day_number - 1)
        context_lines.append(f"\nDay {day_number} ({current_date.strftime('%Y-%m-%d')}):")

        day_places = []
        visit_sequence_counter = 1
        for i, slot in enumerate(day_plan["slots"]):
            slot_key = build_slot_key(day_number, i)
            places = fetched_places.get(slot_key, [])
            if places:
                place = places[0]
                context_lines.append(f"- {slot['section']}: {place['name']} (키워드: {slot['keyword']})")

                if planning_preference == PlanningPreference.PLANNED:
                    visit_time = None
                else:
                    visit_time = slot["section"]
                geometry = place.get("geometry") or {}
                place_url = place.get("url")
                if not place_url and place.get("place_id"):
                    place_url = (
                        "https://www.google.com/maps/search/?api=1&query="
                        f"{place['name']}&query_place_id={place.get('place_id')}"
                    )

                place_payload = {
                    "place_name": place["name"],
                    "place_id": place.get("place_id"),
                    "address": place.get("address"),
                    "latitude": geometry.get("latitude"),
                    "longitude": geometry.get("longitude"),
                    "place_url": place_url,
                    "description": f"{place['name']}에서 즐기는 대표 활동입니다.",
                    "visit_sequence": visit_sequence_counter,
                    "visit_time": visit_time,
                }
                if planning_preference == PlanningPreference.PLANNED:
                    place_payload["section"] = slot.get("section")
                day_places.append(place_payload)
                visit_sequence_counter += 1

        daily_places_for_schema.append(
            {"day_number": day_number, "daily_date": current_date.isoformat(), "places": day_places}
        )

    return "\n".join(context_lines), daily_places_for_schema


async def _fill_visit_times_with_llm(daily_places: list[dict]) -> list[dict]:
    """LLM을 통해 방문 시각을 채웁니다."""
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
        "전체 일정과 이동 동선을 고려해 각 장소의 방문 시각을 24시간 HH:MM 형식으로 작성하세요\n"
        "section_hint는 참고용이며 실제 시간은 이동 시간과 동선을 고려해 자연스럽게 배치하세요\n"
        "하루 시작 시각은 09:00이며 visit_sequence 순서를 지키고 시간은 점진적으로 증가해야 합니다\n"
        "입력에 없는 장소를 추가하거나 방문 순서를 바꾸지 말고 결과 과정은 출력하지 말고 JSON만 반환하세요"
    )
    user_prompt = (
        "아래 장소 목록을 기반으로 방문 시각을 채워주세요\n"
        "시작 시각: 09:00\n"
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
        content = strip_code_fence(response.content)
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
    """모든 정보를 종합해 최종 로드맵을 생성합니다."""
    if state.get("error"):
        return state

    try:
        itinerary_context, daily_places = _prepare_final_context(state)
        course_request = CourseRequest.model_validate(state["course_request"])
        if course_request.planning_preference == PlanningPreference.PLANNED:
            daily_places = await _fill_visit_times_with_llm(daily_places)

        parser = PydanticOutputParser(pydantic_object=CourseResponseLLMOutput)

        system_prompt = (
            "당신은 전문 여행 플래너입니다. 주어진 여행 정보와 확정된 장소 목록을 바탕으로 "
            "사용자를 위한 최종 여행 로드맵을 완성하는 역할을 합니다\n"
            "창의적인 여행 제목과 매력적인 코스가 사용자에게 전달될 수 있도록 설명을 포함하세요\n"
            "출력은 반드시 제공된 JSON 스키마를 엄격히 따라야 합니다"
        )
        human_prompt_template = (
            "## 사용자 요청\n"
            "{course_request}\n\n"
            "## 확정된 일자별 장소 목록\n"
            "{itinerary_context}\n\n"
            "## 생성 작업 가이드\n"
            "1. '사용자 요청'을 참고하여 전체 여행을 아우르는 창의적이고 매력적인 `title`을 생성해주세요. "
            "(반드시 한국어로 작성하되 10자 이내로 간결히 작성하고, 여행지 또는 도시명을 포함해주세요)\n"
            "2. 로드맵을 한 줄로 요약한 `summary`를 한국어로 작성해주세요. (1문장)\n"
            "3. 전체 일정에서 연상되는 핵심 키워드 3~5개를 `tags`에 한국어로 작성해주세요.\n"
            "4. 사용자 요청과 확정된 장소 목록을 모두 고려하여 왜 이 코스가 사용자에게 최적인지 "
            "설명하는 `llm_commentary`를 작성해주세요. (2-3문장)\n"
            "5. 사용자가 바로 입력할 수 있는 다음 행동 문장을 `next_action_suggestion` JSON 배열로 작성해주세요. "
            "(2~3개, 사용자 요청과 일정 내용을 반영해 자연스럽게 작성하고 예시 문장은 그대로 출력하지 마세요. "
            '예시 형식: "오늘 숙소 예약까지 마치고 2일차 일정을 조정해줘.", '
            '"지금 로드맵에 맞춰 대중교통 이용 방법도 알려줘.")\n\n'
            "## 출력 형식\n"
            "{format_instructions}"
        )

        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt_template)])
        messages = prompt.format_messages(
            course_request=course_request,
            itinerary_context=itinerary_context,
            format_instructions=parser.get_format_instructions(),
        )

        response = await get_llm().ainvoke(messages)
        content = strip_code_fence(response.content)

        trip_days = state["trip_days"]
        llm_output = parser.parse(content).model_dump()

        final_roadmap = {
            "start_date": course_request.start_date.isoformat(),
            "end_date": course_request.end_date.isoformat(),
            "trip_days": trip_days,
            "nights": trip_days - 1 if trip_days > 0 else 0,
            "people_count": course_request.people_count,
            **llm_output,
            "itinerary": daily_places,
        }

        return {**state, "final_roadmap": final_roadmap}

    except Exception as exc:
        logger.error(f"최종 로드맵 생성 실패: {exc}", exc_info=True)
        return {**state, "error": f"최종 로드맵 생성에 실패했습니다: {exc}"}
