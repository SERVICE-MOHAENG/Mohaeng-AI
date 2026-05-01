"""로드맵 최종 합성 노드."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.geo import GeoRectangle
from app.core.job_log_context import append_job_log
from app.core.llm_router import Stage, ainvoke
from app.core.logger import get_logger
from app.core.place_category import resolve_place_category
from app.core.region_bbox import get_region_bbox
from app.core.route_optimizer import is_food_anchor, optimize_daily_route
from app.core.timeout_policy import get_timeout_policy
from app.core.visit_time_policy import VisitTimeOutputMode, apply_visit_time_policy, build_visit_time_policy_config
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_slot_key, strip_code_fence
from app.schemas.course import CourseRequest, CourseResponseLLMOutput
from app.schemas.enums import PlanningPreference
from app.services.webhook_notification import notify_pipeline_event

logger = get_logger(__name__)

_SECTION_VISIT_TIME_MAP = {
    "MORNING": "09:00",
    "LUNCH": "12:00",
    "AFTERNOON": "14:00",
    "DINNER": "18:00",
    "EVENING": "20:00",
    "NIGHT": "22:00",
}
_DEFAULT_VISIT_TIME = "09:00"


async def _notify_pipeline_event_best_effort(**kwargs) -> None:
    """Discord 웹훅 알림은 실패해도 로드맵 합성 흐름을 막지 않습니다."""
    try:
        await notify_pipeline_event(**kwargs)
    except Exception as exc:
        logger.warning(
            "Roadmap finalize webhook failed: event_type=%s stage=%s status=%s error=%s",
            kwargs.get("event_type"),
            kwargs.get("stage"),
            kwargs.get("status"),
            exc,
        )


def _select_place_in_region(places: list[dict], region_bbox: GeoRectangle | None) -> dict | None:
    """bbox 내 첫 번째 장소를 반환합니다. bbox 내 장소가 없으면 None을 반환합니다."""
    if not places:
        return None
    if not region_bbox:
        return places[0]
    for place in places:
        geometry = place.get("geometry") or {}
        lat = geometry.get("latitude")
        lng = geometry.get("longitude")
        if lat is not None and lng is not None and region_bbox.contains(lat, lng):
            return place
    logger.warning(
        "No place found within region bbox: candidate_count=%d bbox=(%s,%s)-(%s,%s)",
        len(places),
        region_bbox.min_lat,
        region_bbox.min_lng,
        region_bbox.max_lat,
        region_bbox.max_lng,
    )
    return None


class PlaceDetailSlot(BaseModel):
    """방문 순서별 상세 정보 모델."""

    visit_sequence: int = Field(..., ge=1, description="방문 순서")
    description: str | None = Field(None, description="장소에 대한 한 줄 설명")


class PlaceDetailDay(BaseModel):
    """일자별 상세 정보 모델."""

    day_number: int = Field(..., ge=1, description="여행 일자")
    places: list[PlaceDetailSlot] = Field(..., description="방문 상세 정보 목록")


class PlaceDetailPlan(BaseModel):
    """LLM이 생성한 장소 상세 결과 모델."""

    days: list[PlaceDetailDay] = Field(..., description="일자별 장소 상세 결과")


def _fallback_grace_timeout(timeout_seconds: int) -> int:
    """ainvoke 내부 fallback 시도 여유를 위해 외부 wait_for 타임아웃을 확장합니다."""
    return max(1, int(timeout_seconds) * 2)


def _visit_time_from_section(section: str | None) -> str:
    """스켈레톤 section을 대략적인 방문 시각으로 변환합니다."""
    key = str(section or "").strip().upper()
    return _SECTION_VISIT_TIME_MAP.get(key, _DEFAULT_VISIT_TIME)


def _resolve_visit_time_output_mode(planning_preference: PlanningPreference) -> VisitTimeOutputMode:
    if planning_preference == PlanningPreference.PLANNED:
        return VisitTimeOutputMode.HHMM
    return VisitTimeOutputMode.SECTION_EN


def _apply_route_and_visit_time_policy(daily_places: list[dict], course_request: CourseRequest) -> list[dict]:
    """일자별 장소 순서를 최적화하고 visit_sequence/visit_time을 재계산합니다."""
    output_mode = _resolve_visit_time_output_mode(course_request.planning_preference)
    policy_config = build_visit_time_policy_config()
    total_before = sum(len(day.get("places", [])) for day in daily_places)
    changed_days: list[int] = []
    warnings: list[str] = []

    for day in daily_places:
        places = day.get("places", [])
        if not places:
            continue

        before_place_ids = [place.get("place_id") or place.get("place_name") for place in places]
        optimized_places = optimize_daily_route(places)
        after_place_ids = [place.get("place_id") or place.get("place_name") for place in optimized_places]
        if before_place_ids != after_place_ids:
            changed_days.append(day.get("day_number"))

        for index, place in enumerate(optimized_places, start=1):
            section = place.get("section")
            place["visit_sequence"] = index
            place.pop("visit_time", None)
            if section and is_food_anchor(place):
                place["section_hint"] = section
            place.pop("section", None)

        resolved_places, new_warnings = apply_visit_time_policy(
            optimized_places,
            day_number=day.get("day_number"),
            config=policy_config,
            output_mode=output_mode,
        )
        day["places"] = resolved_places
        warnings.extend(new_warnings)

    append_job_log(
        "route_optimize",
        f"days_changed={changed_days} total_places={total_before} "
        f"visit_time_mode={output_mode.value} warnings={len(warnings)}",
    )
    return daily_places


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

    context_lines = []
    daily_places_for_schema = []
    for day_plan in skeleton_plan:
        day_number = day_plan["day_number"]
        day_region = day_plan.get("region")
        day_region_bbox = get_region_bbox(day_region)
        current_date = course_request.start_date + timedelta(days=day_number - 1)
        context_lines.append(f"\nDay {day_number} ({current_date.strftime('%Y-%m-%d')}):")

        day_places = []
        visit_sequence_counter = 1
        for i, slot in enumerate(day_plan["slots"]):
            slot_key = build_slot_key(day_number, i)
            places = fetched_places.get(slot_key, [])
            if places:
                place = _select_place_in_region(places, day_region_bbox)
                if place is None:
                    continue
                section = slot.get("section")
                display_name = place.get("display_name") or place["name"]

                geometry = place.get("geometry") or {}
                place_url = place.get("url")
                if not place_url and place.get("place_id"):
                    place_url = (
                        "https://www.google.com/maps/search/?api=1&query="
                        f"{display_name}&query_place_id={place.get('place_id')}"
                    )

                day_places.append(
                    {
                        "place_name": display_name,
                        "original_place_name": place.get("name"),
                        "place_id": place.get("place_id"),
                        "address": place.get("address"),
                        "latitude": geometry.get("latitude"),
                        "longitude": geometry.get("longitude"),
                        "place_url": place_url,
                        "place_category": place.get("place_category")
                        or resolve_place_category(place.get("primary_type"), place.get("types") or []).value,
                        "description": f"{display_name}에서 즐기는 대표 활동입니다.",
                        "visit_sequence": visit_sequence_counter,
                        "visit_time": _visit_time_from_section(section),
                        "section": section,
                    }
                )
                visit_sequence_counter += 1

        daily_places_for_schema.append(
            {"day_number": day_number, "daily_date": current_date.isoformat(), "places": day_places}
        )

    daily_places_for_schema = _apply_route_and_visit_time_policy(daily_places_for_schema, course_request)
    context_lines = []
    for day in daily_places_for_schema:
        context_lines.append(f"\nDay {day['day_number']} ({day['daily_date']}):")
        for place in day.get("places", []):
            context_lines.append(
                f"- #{place.get('visit_sequence')} {place.get('visit_time')}: {place.get('place_name')}"
            )

    return "\n".join(context_lines), daily_places_for_schema


def _safe_next_action_suggestions(trip_days: int) -> list[str]:
    """시스템 기능과 100% 일치하는 다음 행동 문장을 반환합니다."""
    suggestions = [
        "이 로드맵을 일정 밀도만 조정해서 다시 만들어줘.",
        "이 로드맵의 이동 동선과 구성 이유를 설명해줘.",
    ]
    if trip_days >= 2:
        suggestions.append("2일차 일정을 더 자세히 설명해줘.")
    else:
        suggestions.append("이 일정의 핵심 포인트를 더 자세히 설명해줘.")
    return suggestions


def _format_priority_notes(notes: str | None) -> str:
    normalized = str(notes or "").strip()
    return normalized if normalized else "없음"


def _build_summary_prompt_messages(
    course_request_payload: dict,
    itinerary_context: str,
    priority_notes: str,
    parser: PydanticOutputParser,
) -> list:
    system_prompt = (
        "당신은 전문 여행 플래너입니다. 주어진 여행 정보와 확정된 장소 목록을 바탕으로 "
        "사용자를 위한 최종 여행 로드맵을 완성하는 역할을 합니다\n"
        "창의적인 여행 제목과 매력적인 코스가 사용자에게 전달될 수 있도록 설명을 포함하세요\n"
        "'최우선 사용자 메모'가 있으면 title, summary, tags, llm_commentary 전반에서 가장 먼저 반영하세요\n"
        "다른 일반 선호와 충돌하면 최우선 사용자 메모를 우선 해석하고, 누락 없이 결과에 드러나게 하세요\n"
        "출력은 반드시 제공된 JSON 스키마를 엄격히 따라야 합니다"
    )
    human_prompt_template = (
        "## 최우선 사용자 메모\n"
        "{priority_notes}\n\n"
        "## 사용자 요청 전체 정보\n"
        "{course_request}\n\n"
        "## 확정된 일자별 장소 목록\n"
        "{itinerary_context}\n\n"
        "## 생성 작업 가이드\n"
        "0. '최우선 사용자 메모'가 있으면 가장 중요한 제약으로 간주하고, "
        "제목/요약/태그/코멘터리에 반복적으로 드러나게 해주세요.\n"
        "1. '최우선 사용자 메모'와 '사용자 요청 전체 정보'를 참고하여 "
        "전체 여행을 아우르는 창의적이고 매력적인 `title`을 생성해주세요. "
        "(반드시 한국어로 작성하되 10자 이내로 간결히 작성하고, 여행지 또는 도시명을 포함해주세요)\n"
        "2. 로드맵을 한 줄로 요약한 `summary`를 한국어로 작성해주세요. (1문장)\n"
        "3. 전체 일정에서 연상되는 핵심 키워드 3~5개를 `tags`에 한국어로 작성해주세요.\n"
        "4. '최우선 사용자 메모', 사용자 요청, 확정된 장소 목록을 모두 고려하여 왜 이 코스가 사용자에게 최적인지 "
        "설명하는 `llm_commentary`를 작성해주세요. (2-3문장)\n"
        "5. 사용자가 바로 입력할 수 있는 다음 행동 문장을 `next_action_suggestion` JSON 배열로 작성해주세요. "
        "(2~3개, 반드시 우리 시스템이 가능한 작업만 포함해야 합니다. "
        "가능한 작업: 로드맵 생성/재생성/일정 조정 요청, 로드맵 내용에 대한 질문. "
        "불가능한 작업: 숙소/항공/렌터카/티켓 예약, 결제, 구매, 환전, 보험, 외부 서비스 연동. "
        "예시 문장은 그대로 출력하지 마세요.)\n\n"
        "## 출력 형식\n"
        "{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt_template)])
    return prompt.format_messages(
        priority_notes=priority_notes,
        course_request=course_request_payload,
        itinerary_context=itinerary_context,
        format_instructions=parser.get_format_instructions(),
    )


async def _fill_place_descriptions_with_llm(daily_places: list[dict]) -> list[dict]:
    """LLM을 통해 장소 description을 채웁니다."""
    parser = PydanticOutputParser(pydantic_object=PlaceDetailPlan)
    timeout_seconds = get_timeout_policy().llm_timeout_seconds
    wait_timeout_seconds = _fallback_grace_timeout(timeout_seconds)

    def _fallback_description(place: dict) -> str:
        place_name = place.get("place_name") or "장소"
        return f"{place_name}에서 즐기는 대표 활동입니다."

    def _apply_fallback() -> list[dict]:
        for day in daily_places:
            for place in day.get("places", []):
                if not place.get("description"):
                    place["description"] = _fallback_description(place)
        return daily_places

    if not any(day.get("places") for day in daily_places):
        return _apply_fallback()

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
                        "address": place.get("address"),
                        "latitude": place.get("latitude"),
                        "longitude": place.get("longitude"),
                        "place_url": place.get("place_url"),
                    }
                    for place in day.get("places", [])
                ],
            }
        )

    system_prompt = (
        "당신은 여행 일정의 장소 설명을 작성하는 전문가입니다.\n"
        "모든 장소에 대해 한국어 한 문장으로 description을 작성하세요.\n"
        "description은 장소명 또는 대표 활동을 포함하고 30자 내외로 간결하게 작성하세요.\n"
        "과장, 이모지, 해시태그, 불확실한 정보는 피하고 입력 정보에 기반해 작성하세요.\n"
        "입력에 없는 장소를 추가하거나 방문 순서를 바꾸지 말고 JSON만 반환하세요."
    )
    user_prompt = (
        "아래 장소 목록을 기반으로 각 장소의 description을 채워주세요.\n입력 데이터:\n{places}\n\n{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    messages = prompt.format_messages(
        places=json.dumps(input_days, ensure_ascii=False, indent=2),
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = await asyncio.wait_for(
            ainvoke(Stage.ROADMAP_PLACE_DETAIL, messages, timeout_seconds=timeout_seconds),
            timeout=wait_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Place description LLM timed out: per_call_timeout=%s wait_timeout=%s",
            timeout_seconds,
            wait_timeout_seconds,
        )
        return _apply_fallback()
    except Exception:
        logger.exception("Place description LLM call failed")
        return _apply_fallback()

    try:
        content = strip_code_fence(response.content)
        detail_plan = parser.parse(content)
    except Exception:
        logger.exception("Place description parse failed")
        return _apply_fallback()

    detail_map = {(day.day_number, slot.visit_sequence): slot for day in detail_plan.days for slot in day.places}
    for day in daily_places:
        day_number = day.get("day_number")
        for place in day.get("places", []):
            key = (day_number, place.get("visit_sequence"))
            detail = detail_map.get(key)
            description = (detail.description or "").strip() if detail else ""
            place["description"] = description or _fallback_description(place)

    return daily_places


async def synthesize_final_roadmap(state: RoadmapState) -> RoadmapState:
    """모든 정보를 종합해 최종 로드맵을 생성합니다."""
    if state.get("error"):
        return state

    try:
        itinerary_context, daily_places = _prepare_final_context(state)
        course_request = CourseRequest.model_validate(state["course_request"])
        daily_places = await _fill_place_descriptions_with_llm(daily_places)
        desc_count = sum(1 for d in daily_places for p in d.get("places", []) if p.get("description"))
        append_job_log("finalize_desc", f"place_descriptions_filled={desc_count}")

        append_job_log("finalize_time", f"strategy=visit_time_policy preference={course_request.planning_preference}")

        course_request_payload = course_request.model_dump(mode="json")
        priority_notes = _format_priority_notes(course_request.notes)

        parser = PydanticOutputParser(pydantic_object=CourseResponseLLMOutput)
        messages = _build_summary_prompt_messages(
            course_request_payload=course_request_payload,
            itinerary_context=itinerary_context,
            priority_notes=priority_notes,
            parser=parser,
        )

        timeout_seconds = get_timeout_policy().llm_timeout_seconds
        wait_timeout_seconds = _fallback_grace_timeout(timeout_seconds)
        response = await asyncio.wait_for(
            ainvoke(Stage.ROADMAP_SUMMARY, messages, timeout_seconds=timeout_seconds),
            timeout=wait_timeout_seconds,
        )
        content = strip_code_fence(response.content)

        trip_days = state["trip_days"]
        llm_output = parser.parse(content).model_dump()
        llm_output["next_action_suggestion"] = _safe_next_action_suggestions(trip_days)

        final_roadmap = {
            "start_date": course_request.start_date.isoformat(),
            "end_date": course_request.end_date.isoformat(),
            "trip_days": trip_days,
            "nights": trip_days - 1 if trip_days > 0 else 0,
            "people_count": course_request.people_count,
            **llm_output,
            "itinerary": daily_places,
        }

        total_places = sum(len(d.get("places", [])) for d in daily_places)
        append_job_log("finalize", f"title={final_roadmap.get('title', '')} places={total_places}")
        return {**state, "final_roadmap": final_roadmap}

    except Exception as exc:
        append_job_log("finalize", f"error: {type(exc).__name__} (see server logs)")
        logger.error("최종 로드맵 생성 실패: %s", exc, exc_info=True)
        await _notify_pipeline_event_best_effort(
            event_type="roadmap_finalize_failed",
            severity="error",
            stage="roadmap.finalize",
            status="FAILED",
            title="❌ Finalize Stage Failed",
            message="최종 로드맵 생성 중 오류가 발생했습니다.",
            error=type(exc).__name__,
        )
        return {**state, "error": f"최종 로드맵 생성에 실패했습니다: {exc}"}
