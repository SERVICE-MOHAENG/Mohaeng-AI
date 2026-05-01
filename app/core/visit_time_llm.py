"""visit_time 제안 LLM 호출 유틸."""

from __future__ import annotations

import asyncio
import json

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm_router import Stage, ainvoke
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy

logger = get_logger(__name__)


class VisitTimeProposalSlot(BaseModel):
    """방문 순서별 visit_time 제안."""

    visit_sequence: int = Field(..., ge=1, description="방문 순서")
    visit_time: str | None = Field(None, description="방문 시각 (08:00~24:00 범위의 24시간 HH:MM)")


class VisitTimeProposalDay(BaseModel):
    """일자별 visit_time 제안."""

    day_number: int = Field(..., ge=1, description="여행 일자")
    places: list[VisitTimeProposalSlot] = Field(..., description="visit_time 제안 목록")


class VisitTimeProposalPlan(BaseModel):
    """LLM visit_time 제안 결과 모델."""

    days: list[VisitTimeProposalDay] = Field(..., description="일자별 visit_time 제안")


def _strip_code_fence(text: str) -> str:
    content = (text or "").strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) > 1:
            content = parts[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
    return content.strip()


def _build_input_days(daily_places: list[dict]) -> list[dict]:
    input_days: list[dict] = []
    for day in daily_places:
        input_days.append(
            {
                "day_number": day.get("day_number"),
                "daily_date": day.get("daily_date"),
                "places": [
                    {
                        "visit_sequence": place.get("visit_sequence"),
                        "place_name": place.get("place_name"),
                        "section_hint": place.get("section") or place.get("section_hint"),
                        "time_hint": place.get("visit_time"),
                        "address": place.get("address"),
                        "latitude": place.get("latitude"),
                        "longitude": place.get("longitude"),
                    }
                    for place in day.get("places", [])
                ],
            }
        )
    return input_days


def _to_proposal_map(plan: VisitTimeProposalPlan) -> dict[int, dict[int, str]]:
    proposal_map: dict[int, dict[int, str]] = {}
    for day in plan.days:
        day_map: dict[int, str] = {}
        for slot in day.places:
            visit_time = (slot.visit_time or "").strip()
            if visit_time:
                day_map[slot.visit_sequence] = visit_time
        if day_map:
            proposal_map[day.day_number] = day_map
    return proposal_map


def _fallback_grace_timeout(timeout_seconds: int) -> int:
    """ainvoke 내부 fallback 시도 여유를 위해 외부 wait_for 타임아웃을 확장합니다."""
    return max(1, int(timeout_seconds) * 2)


async def propose_visit_times_for_days(
    daily_places: list[dict],
    *,
    stage: Stage = Stage.CHAT_VISIT_TIME,
    timeout_seconds: int | None = None,
) -> dict[int, dict[int, str]]:
    """일자별 장소 입력을 받아 visit_sequence -> HH:MM 제안 맵을 반환합니다."""
    if not daily_places:
        return {}
    if not any(day.get("places") for day in daily_places):
        return {}

    parser = PydanticOutputParser(pydantic_object=VisitTimeProposalPlan)
    policy = get_timeout_policy()
    resolved_timeout = timeout_seconds or policy.llm_timeout_seconds
    wait_timeout = _fallback_grace_timeout(resolved_timeout)
    input_days = _build_input_days(daily_places)

    system_prompt = (
        "당신은 여행 일정의 visit_time을 배치하는 전문가입니다.\n"
        "출력은 JSON만 반환하고, visit_time은 반드시 24시간 HH:MM 형식을 사용하세요.\n"
        "visit_time은 반드시 08:00 이상 24:00 이하로 출력하세요.\n"
        "08:00보다 이른 시간과 24:00보다 늦은 시간은 절대 출력하지 마세요.\n"
        "24:00은 하루 종료 시각으로만 사용할 수 있고 24:01, 25:00 같은 값은 금지입니다.\n"
        "visit_sequence 순서를 지키고 시간이 감소하지 않도록 동일하거나 점진적으로 증가해야 합니다.\n"
        "동일한 일차에서 최대 10개 장소까지 자연스럽고 현실적으로 배치하세요.\n"
        "visit_time의 분(MM)은 반드시 '00' 또는 '30' 중 하나를 사용하여 30분 단위로 배치하세요.\n"
        "section_hint, time_hint는 참고용이며 이동 동선을 고려해 자연스럽게 배치하세요.\n"
        "입력에 없는 장소를 추가하거나 순서를 바꾸지 마세요.\n"
        "운영시간 데이터가 없으므로 실제 영업시간을 단정하지 마세요."
    )
    user_prompt = (
        "아래 일정 데이터의 각 장소에 대한 visit_time을 제안해주세요.\n"
        "시작 시각 기준: 09:00\n"
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
        response = await asyncio.wait_for(
            ainvoke(stage, messages, timeout_seconds=resolved_timeout),
            timeout=wait_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Visit time LLM timed out: stage=%s per_call_timeout=%s wait_timeout=%s",
            stage.value,
            resolved_timeout,
            wait_timeout,
        )
        return {}
    except Exception:
        logger.exception("Visit time LLM call failed: stage=%s", stage.value)
        return {}

    try:
        content = _strip_code_fence(response.content)
        parsed = parser.parse(content)
        return _to_proposal_map(parsed)
    except Exception:
        logger.exception("Visit time proposal parse failed")
        return {}
