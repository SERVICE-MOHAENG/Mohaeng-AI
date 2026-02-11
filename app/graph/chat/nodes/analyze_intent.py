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
   - REPLACE/ADD 시 Google Places API Text Search(textQuery)에 직접 넣을 검색어를 작성하세요.
   - REMOVE/MOVE 시 search_keyword는 null로 설정하세요.
   - search_keyword 형식은 반드시 "<지역명 또는 동네> <장소명/장소유형>" 입니다.
   - search_keyword에는 target_day의 위치 기반 컨텍스트(지역명)를 반드시 포함하세요.
   - 예시: "서울 성수 브런치 카페", "도쿄 시부야 스시 오마카세"

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
Day별 위치 컨텍스트:
{day_region_context}

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


def _contains_hangul(text: str) -> bool:
    """문자열에 한글이 포함되어 있는지 확인합니다."""
    return bool(re.search(r"[가-힣]", text))


def _extract_korean_region_hint(address: str) -> str | None:
    """국내 주소에서 `시/도` 및 가능하면 `구/군`까지 추출합니다."""
    leading = address.split(",")[0].strip()
    tokens = [token.strip() for token in leading.split() if token.strip()]
    if not tokens:
        return None

    city_suffixes = ("특별시", "광역시", "특별자치시", "특별자치도", "시", "도")
    local_suffixes = ("구", "군", "읍", "면", "동")

    for index, token in enumerate(tokens):
        if token.endswith(city_suffixes):
            if index + 1 < len(tokens) and tokens[index + 1].endswith(local_suffixes):
                return f"{token} {tokens[index + 1]}"
            return token

    for token in tokens[:4]:
        if token.endswith(local_suffixes):
            return token

    return tokens[0]


def _is_postal_code(token: str) -> bool:
    """우편번호 형태인지 판별합니다."""
    normalized = token.strip().upper()
    if re.fullmatch(r"\d{4,10}", normalized):
        return True
    if re.fullmatch(r"\d{5}(-\d{4})?", normalized):
        return True
    if re.fullmatch(r"[A-Z]\d[A-Z]\s?\d[A-Z]\d", normalized):
        return True
    return False


def _extract_english_city_country_hint(address: str) -> str | None:
    """영문 콤마 주소에서 `도시, 국가` 형태의 힌트를 추출합니다."""
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if len(parts) < 2:
        return None

    country = parts[-1]
    if not re.search(r"[A-Za-z]", country):
        return None

    for part in reversed(parts[:-1]):
        token = part.strip()
        if not token:
            continue
        if re.fullmatch(r"[A-Z]{2,3}", token):
            continue
        if _is_postal_code(token):
            continue
        if token[0].isdigit():
            continue
        if not re.search(r"[A-Za-z]", token):
            continue
        return f"{token}, {country}"

    return country


def _extract_generic_region_hint(address: str) -> str | None:
    """기타 포맷 주소에서 지역 힌트를 추출합니다."""
    leading = address.split(",")[0].strip()
    tokens = [token.strip() for token in leading.split() if token.strip()]
    if not tokens:
        return None

    for token in tokens[:4]:
        lowered = token.lower()
        if lowered.endswith(("city", "province", "prefecture", "state", "county")):
            return token
        if not token[0].isdigit():
            return token

    return None


def _extract_region_hint_from_address(address: str) -> str | None:
    """주소 문자열에서 지역 힌트를 추출합니다."""
    text = (address or "").strip()
    if not text:
        return None

    if _contains_hangul(text):
        korean_hint = _extract_korean_region_hint(text)
        if korean_hint:
            return korean_hint

    english_hint = _extract_english_city_country_hint(text)
    if english_hint:
        return english_hint

    return _extract_generic_region_hint(text)


def _build_day_region_hints(itinerary: dict) -> dict[int, str]:
    """일자별 대표 지역 힌트를 수집합니다."""
    hints: dict[int, str] = {}
    for day in itinerary.get("itinerary", []):
        day_number = day.get("day_number")
        if not isinstance(day_number, int):
            continue

        for place in day.get("places", []):
            region_hint = _extract_region_hint_from_address(str(place.get("address") or ""))
            if region_hint:
                hints[day_number] = region_hint
                break
    return hints


def _format_day_region_context(day_region_hints: dict[int, str]) -> str:
    """프롬프트용 Day별 지역 컨텍스트 문자열을 생성합니다."""
    if not day_region_hints:
        return "(주소 기반 지역 힌트를 찾지 못했습니다.)"
    lines = [f"- Day {day}: {region}" for day, region in sorted(day_region_hints.items())]
    return "\n".join(lines)


def _ensure_search_keyword_contains_region(
    intent_draft: ChatIntentDraft, day_region_hints: dict[int, str]
) -> ChatIntentDraft:
    """REPLACE/ADD 검색어에 지역 힌트를 강제 포함합니다."""
    if intent_draft.op not in (ChatOperation.REPLACE, ChatOperation.ADD):
        return intent_draft

    keyword = (intent_draft.search_keyword or "").strip()
    if not keyword:
        return intent_draft

    region_hint = day_region_hints.get(intent_draft.target_day)
    if not region_hint:
        return intent_draft

    if region_hint.lower() in keyword.lower():
        return intent_draft

    return intent_draft.model_copy(update={"search_keyword": f"{region_hint} {keyword}"})


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
    day_region_context: str,
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
        day_region_context=day_region_context,
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
    day_region_hints = _build_day_region_hints(current_itinerary)
    day_region_context = _format_day_region_context(day_region_hints)

    intent_type = _classify_intent_type(itinerary_table, history_context, user_query)
    if intent_type == "GENERAL_CHAT":
        return {**state, "intent_type": "GENERAL_CHAT"}

    try:
        intent_draft = _parse_modification_intent(
            itinerary_table=itinerary_table,
            history_context=history_context,
            day_region_context=day_region_context,
            user_query=user_query,
        )
        intent_draft = _ensure_search_keyword_contains_region(intent_draft, day_region_hints)
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
