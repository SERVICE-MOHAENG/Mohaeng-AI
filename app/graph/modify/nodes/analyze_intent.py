"""사용자 수정 요청 의도 분석 LLM 노드."""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import get_logger
from app.graph.modify.llm import get_llm
from app.graph.modify.state import ModifyState
from app.graph.roadmap.utils import strip_code_fence
from app.schemas.enums import ModifyStatus
from app.schemas.modify import ModifyIntent

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
당신은 여행 로드맵 수정 요청을 분석하는 전문 어시스턴트입니다.
사용자의 자연어 수정 요청을 분석하여 구조화된 수정 의도(Intent)를 추출하세요.

## 규칙

1. **Operation 분류**
   - REPLACE: 기존 장소를 다른 장소로 교체
   - ADD: 특정 위치에 새 장소 추가
   - REMOVE: 특정 장소 삭제
   - MOVE: 같은 Day 내 장소 순서 변경

2. **Entity Linking**
   - "점심", "저녁", "카페" 등 표현을 아래 매핑 테이블의 (day_number, visit_sequence)로 매핑하세요.
   - "거기", "아까 그거" 등 지시어는 대화 맥락(session_history)을 참고하여 해소하세요.

3. **Search Keyword 추출**
   - REPLACE/ADD 시 Google Places API 검색에 사용할 키워드를 추출하세요.
   - REMOVE/MOVE 시 search_keyword는 null로 설정하세요.

6. **MOVE 이동 목적지**
   - MOVE 시 destination_day(이동 목적지 일자)와 destination_index(이동 목적지 순서)를 반드시 설정하세요.
   - REPLACE/ADD/REMOVE 시 destination_day와 destination_index는 null로 설정하세요.

4. **복합 요청 처리**
   - 두 가지 이상의 수정이 감지되면 **첫 번째 요청만** 추출하세요.
   - is_compound를 true로 설정하세요.

5. **모호성 감지**
   - 대상을 특정할 수 없으면 needs_clarification을 true로 설정하세요.
   - reasoning에 어떤 부분이 모호한지 구체적으로 작성하세요.
   - 예: "식당 바꿔줘" 인데 식당이 2곳 이상인 경우

## 현재 로드맵 매핑 테이블

{itinerary_table}

## 출력 형식

{format_instructions}
"""

USER_PROMPT = """\
{history_context}\
사용자 요청: {user_query}
"""


def _build_itinerary_table(itinerary: dict) -> str:
    """로드맵 데이터를 (day_number, visit_sequence, place_name) 매핑 테이블로 변환합니다."""
    lines: list[str] = []
    days = itinerary.get("itinerary", [])
    for day in days:
        day_number = day.get("day_number", "?")
        places = day.get("places", [])
        for place in places:
            seq = place.get("visit_sequence", "?")
            name = place.get("place_name", "알 수 없음")
            visit_time = place.get("visit_time", "")
            lines.append(f"- Day {day_number}, #{seq}: {name} ({visit_time})")
    return "\n".join(lines) if lines else "(로드맵이 비어 있습니다)"


def _build_history_context(session_history: list[dict]) -> str:
    """세션 히스토리를 프롬프트 컨텍스트로 변환합니다."""
    if not session_history:
        return ""
    lines: list[str] = []
    for msg in session_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"[{role}] {content}")
    return "최근 대화 맥락:\n" + "\n".join(lines) + "\n\n"


def analyze_intent(state: ModifyState) -> ModifyState:
    """사용자의 수정 요청에서 구조화된 의도(ModifyIntent)를 추출합니다."""
    current_itinerary = state.get("current_itinerary")
    user_query = state.get("user_query")
    session_history = state.get("session_history", [])

    if not current_itinerary or not user_query:
        return {**state, "error": "의도 분석에는 current_itinerary와 user_query가 필요합니다."}

    parser = PydanticOutputParser(pydantic_object=ModifyIntent)

    itinerary_table = _build_itinerary_table(current_itinerary)
    history_context = _build_history_context(session_history)

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])

    messages = prompt.format_messages(
        itinerary_table=itinerary_table,
        format_instructions=parser.get_format_instructions(),
        history_context=history_context,
        user_query=user_query,
    )

    try:
        response = get_llm().invoke(messages)
        content = strip_code_fence(response.content)
        intent = parser.parse(content)
    except Exception as exc:
        logger.error("의도 분석 LLM 호출 실패: %s", exc)
        return {**state, "error": "수정 의도 분석에 실패했습니다."}

    if intent.needs_clarification:
        return {
            **state,
            "intent": intent.model_dump(),
            "status": ModifyStatus.ASK_CLARIFICATION,
            "change_summary": intent.reasoning,
        }

    return {**state, "intent": intent.model_dump()}
