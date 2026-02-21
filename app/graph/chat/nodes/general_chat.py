"""일반 대화 응답 생성 노드."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm_router import Stage, invoke
from app.core.logger import get_logger
from app.graph.chat.state import ChatState
from app.schemas.enums import ChatStatus

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
당신은 여행 일정 코치를 맡은 대화형 어시스턴트입니다.
사용자의 질문에 한국어로 간결하고 정확하게 답하세요.

규칙:
- 현재 로드맵 정보와 대화 맥락을 우선 활용합니다.
- 수정 실행은 하지 않고 설명/안내/추천만 제공합니다.
- 확신이 낮은 정보는 단정하지 말고 확인 질문을 제시하세요.
"""

USER_PROMPT = """\
현재 로드맵 요약:
{itinerary_context}

여행자 선호 컨텍스트:
{request_context}

최근 대화 맥락:
{history_context}

사용자 질문:
{user_query}
"""


def _build_history_context(session_history: list[dict]) -> str:
    """세션 히스토리를 프롬프트 컨텍스트 문자열로 변환합니다."""
    if not session_history:
        return "없음"
    lines: list[str] = []
    for message in session_history[-6:]:
        role = message.get("role", "unknown")
        content = (message.get("content", "") or "").strip()
        if content:
            lines.append(f"[{role}] {content}")
    return "\n".join(lines) if lines else "없음"


def _build_itinerary_context(itinerary: dict) -> str:
    """현재 로드맵을 일반 대화용 요약 문자열로 변환합니다."""
    if not itinerary:
        return "로드맵 정보 없음"

    title = itinerary.get("title") or "제목 없음"
    start_date = itinerary.get("start_date") or "?"
    end_date = itinerary.get("end_date") or "?"

    lines = [f"제목: {title}", f"일정: {start_date} ~ {end_date}"]

    days = itinerary.get("itinerary", []) or []
    for day in days[:5]:
        day_number = day.get("day_number", "?")
        places = day.get("places", []) or []
        names = [str(place.get("place_name", "")).strip() for place in places[:4] if place.get("place_name")]
        joined = ", ".join(names) if names else "장소 정보 없음"
        lines.append(f"- Day {day_number}: {joined}")

    return "\n".join(lines)


def _build_request_context(request_context: dict) -> str:
    """요청 기반 선호 정보를 일반 대화 프롬프트용 문자열로 변환합니다."""
    if not request_context:
        return "없음"

    travel_themes = request_context.get("travel_themes") or []
    themes_text = ", ".join([str(theme) for theme in travel_themes]) if travel_themes else "없음"
    lines = [
        f"- 동행자: {request_context.get('companion_type', '없음')}",
        f"- 테마: {themes_text}",
        f"- 일정 밀도: {request_context.get('pace_preference', '없음')}",
        f"- 계획 성향: {request_context.get('planning_preference', '없음')}",
        f"- 목적지 성향: {request_context.get('destination_preference', '없음')}",
        f"- 활동 성향: {request_context.get('activity_preference', '없음')}",
        f"- 우선 가치: {request_context.get('priority_preference', '없음')}",
        f"- 예산: {request_context.get('budget_range', '없음')}",
    ]
    return "\n".join(lines)


def general_chat(state: ChatState) -> ChatState:
    """일반 질문에 대한 대화 응답을 생성합니다."""
    user_query = (state.get("user_query") or "").strip()
    current_itinerary = state.get("current_itinerary") or {}
    session_history = state.get("session_history", [])
    request_context = state.get("request_context", {})

    if not user_query:
        return {
            **state,
            "status": ChatStatus.REJECTED,
            "message": "대화 내용을 찾을 수 없어 응답을 생성하지 못했습니다.",
        }

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])
    messages = prompt.format_messages(
        itinerary_context=_build_itinerary_context(current_itinerary),
        request_context=_build_request_context(request_context),
        history_context=_build_history_context(session_history),
        user_query=user_query,
    )

    try:
        response = invoke(Stage.CHAT_RESPONSE, messages)
        message = response.content.strip()
        if not message:
            message = "질문 의도를 파악했어요. 궁금한 부분을 조금 더 구체적으로 알려주세요."
    except Exception as exc:
        logger.error("일반 대화 응답 생성 실패: %s", exc)
        return {
            **state,
            "status": ChatStatus.REJECTED,
            "message": "대화 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        }

    return {
        **state,
        "status": ChatStatus.GENERAL_CHAT,
        "message": message,
        "diff_keys": [],
    }
