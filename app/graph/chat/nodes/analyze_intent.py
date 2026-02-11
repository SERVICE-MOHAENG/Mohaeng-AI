"""사용자 대화 의도 분류 및 수정 의도 분석 LLM 노드."""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from app.core.logger import get_logger
from app.graph.chat.llm import get_llm
from app.graph.chat.state import ChatState
from app.graph.roadmap.utils import strip_code_fence
from app.schemas.chat import ChatIntent
from app.schemas.enums import ChatOperation, ChatStatus

logger = get_logger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """\
당신은 여행 대화 라우터입니다.
사용자 요청을 아래 두 가지 중 하나로 분류하세요.

- GENERAL_CHAT: 일정 설명/추천/질문/안내 등 일반 대화
- MODIFICATION: 일정 항목의 추가/삭제/교체/순서 이동 등 실제 변경 요청

규칙:
- 단순 정보 질문, 이유 설명, 추천 요청은 GENERAL_CHAT입니다.
- 명시적 변경 동사(바꿔/추가/삭제/옮겨 등)나 수정 의도가 있으면 MODIFICATION입니다.
- 응답은 JSON만 출력하세요.
"""

CLASSIFIER_USER_PROMPT = """\
{history_context}\
현재 로드맵 매핑:
{itinerary_table}

사용자 요청: {user_query}

{format_instructions}
"""

MODIFICATION_SYSTEM_PROMPT = """\
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
   - 단, needs_clarification=true라면 MOVE여도 destination_day와 destination_index는 null이어도 됩니다.

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

MODIFICATION_USER_PROMPT = """\
{history_context}\
사용자 요청: {user_query}
"""


class ChatIntentRoute(BaseModel):
    """대화 라우팅 분류 결과."""

    intent_type: Literal["GENERAL_CHAT", "MODIFICATION"] = Field(..., description="의도 분류 결과")
    reasoning: str = Field(default="", description="분류 근거")


class ChatIntentDraft(BaseModel):
    """수정 의도 초안 모델.

    파싱 실패를 줄이기 위해 최소 제약으로 먼저 파싱한다.
    """

    op: ChatOperation
    target_day: int = Field(ge=1, default=1)
    target_index: int = Field(ge=1, default=1)
    destination_day: int | None = Field(default=None, ge=1)
    destination_index: int | None = Field(default=None, ge=1)
    search_keyword: str | None = None
    reasoning: str = ""
    is_compound: bool = False
    needs_clarification: bool = False


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


def _has_modification_keyword(user_query: str) -> bool:
    """LLM 분류 실패 시 사용할 간단한 수정 의도 키워드 휴리스틱."""
    keywords = (
        "바꿔",
        "변경",
        "수정",
        "추가",
        "삭제",
        "제거",
        "옮겨",
        "이동",
        "순서",
        "replace",
        "add",
        "remove",
        "move",
    )
    normalized = user_query.lower()
    return any(keyword in normalized for keyword in keywords)


def _classify_intent_type(itinerary_table: str, history_context: str, user_query: str) -> str:
    """요청을 GENERAL_CHAT 또는 MODIFICATION으로 분류합니다."""
    parser = PydanticOutputParser(pydantic_object=ChatIntentRoute)
    prompt = ChatPromptTemplate.from_messages([("system", CLASSIFIER_SYSTEM_PROMPT), ("human", CLASSIFIER_USER_PROMPT)])
    messages = prompt.format_messages(
        itinerary_table=itinerary_table,
        history_context=history_context,
        user_query=user_query,
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = get_llm().invoke(messages)
        content = strip_code_fence(response.content)
        route = parser.parse(content)
        return route.intent_type
    except Exception as exc:
        logger.warning("의도 분류 LLM 호출 실패, 휴리스틱으로 대체: %s", exc)
        return "MODIFICATION" if _has_modification_keyword(user_query) else "GENERAL_CHAT"


def _extract_json_object(text: str) -> dict | None:
    """LLM 응답 문자열에서 JSON 객체를 최대한 복구해 파싱합니다."""
    content = strip_code_fence(text)
    if not content:
        return None

    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _parse_modification_intent(
    itinerary_table: str,
    history_context: str,
    user_query: str,
) -> ChatIntentDraft:
    """수정 의도 초안을 파싱합니다. 실패 시 JSON 복구를 시도합니다."""
    parser = PydanticOutputParser(pydantic_object=ChatIntentDraft)
    prompt = ChatPromptTemplate.from_messages(
        [("system", MODIFICATION_SYSTEM_PROMPT), ("human", MODIFICATION_USER_PROMPT)]
    )

    messages = prompt.format_messages(
        itinerary_table=itinerary_table,
        format_instructions=parser.get_format_instructions(),
        history_context=history_context,
        user_query=user_query,
    )

    response = get_llm().invoke(messages)
    content = strip_code_fence(response.content)

    try:
        return parser.parse(content)
    except Exception as exc:
        recovered = _extract_json_object(content)
        if recovered is not None:
            return ChatIntentDraft.model_validate(recovered)
        raise ValueError("수정 의도 응답 파싱에 실패했습니다.") from exc


def analyze_intent(state: ChatState) -> ChatState:
    """사용자 요청을 GENERAL_CHAT 또는 MODIFICATION으로 분류합니다."""
    current_itinerary = state.get("current_itinerary")
    user_query = state.get("user_query")
    session_history = state.get("session_history", [])

    if not current_itinerary or not user_query:
        return {**state, "error": "의도 분석에는 current_itinerary와 user_query가 필요합니다."}

    itinerary_table = _build_itinerary_table(current_itinerary)
    history_context = _build_history_context(session_history)

    intent_type = _classify_intent_type(itinerary_table, history_context, user_query)
    if intent_type == "GENERAL_CHAT":
        return {**state, "intent_type": "GENERAL_CHAT"}

    try:
        intent_draft = _parse_modification_intent(
            itinerary_table=itinerary_table,
            history_context=history_context,
            user_query=user_query,
        )
    except Exception as exc:
        logger.error("의도 분석 LLM 호출 실패: %s", exc)
        return {**state, "error": "수정 의도 분석에 실패했습니다."}

    if intent_draft.needs_clarification:
        return {
            **state,
            "intent_type": "MODIFICATION",
            "intent": intent_draft.model_dump(),
            "status": ChatStatus.ASK_CLARIFICATION,
            "change_summary": intent_draft.reasoning or "요청이 모호하여 확인이 필요합니다.",
        }

    try:
        strict_intent = ChatIntent.model_validate(intent_draft.model_dump())
    except ValidationError:
        return {
            **state,
            "intent_type": "MODIFICATION",
            "intent": intent_draft.model_dump(),
            "status": ChatStatus.ASK_CLARIFICATION,
            "change_summary": intent_draft.reasoning or "수정 대상 확인을 위해 추가 정보가 필요합니다.",
        }

    return {**state, "intent_type": "MODIFICATION", "intent": strict_intent.model_dump()}
