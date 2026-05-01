"""사용자 대화 의도 분류 및 수정 의도 분석 LLM 노드."""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from app.core.job_log_context import append_job_log
from app.core.llm_router import Stage, invoke
from app.core.logger import get_logger
from app.graph.chat.state import ChatState
from app.graph.roadmap.utils import strip_code_fence
from app.schemas.chat import ChatIntent
from app.schemas.enums import ChatOperation, ChatStatus
from app.services.webhook_notification import notify_pipeline_event, schedule_webhook

logger = get_logger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """\
당신은 여행 대화 라우터입니다.
사용자 요청을 아래 두 가지 중 하나로 분류하세요.

- GENERAL_CHAT: 일정 설명/추천/질문/안내 등 일반 대화
- MODIFICATION: 일정 항목의 추가/삭제/교체/순서 이동 등 실제 변경 요청

규칙:
- 단순 정보 질문, 이유 설명, 추천 요청은 GENERAL_CHAT입니다.
- 명시적 변경 동사(바꿔/추가/삭제/옮겨 등)나 수정 의도가 있으면 MODIFICATION입니다.
- MODIFICATION이라면 requested_action과 target_scope도 함께 분류하세요.
- requested_action:
  - DELETE: 삭제 요청
  - ADD: 추가 요청
  - REPLACE: 교체 요청
  - MOVE: 순서/위치 이동 요청
  - UNKNOWN: 수정은 맞지만 유형 불명확
- target_scope:
  - DAY_LEVEL: 일차 자체(예: "1일차 삭제", "2일차를 3일차로 이동", "날짜 변경")
  - DAY_PLACES: 날짜는 유지하고 두 일차에 배치된 장소 묶음만 교체(예: "1일차랑 2일차 일정 바꿔줘")
  - DAY_OPTIMIZE: 단일 일차의 전체 동선을 재정렬(예: "1일차 전체 일정 최적화해줘")
  - ITEM_LEVEL: 일차 내부 장소(visit_sequence/place) 단위
  - UNKNOWN: 단위를 특정할 수 없음
- "1일차 삭제해줘"는 DAY_LEVEL DELETE입니다.
- "1일차랑 2일차 일정 바꿔줘"는 DAY_PLACES REPLACE입니다.
- "1일차 전체 일정 최적화해줘"는 DAY_OPTIMIZE MOVE입니다.
- "2일차 첫 번째 장소를 1일차 마지막으로 옮겨줘"는 ITEM_LEVEL MOVE입니다.
- "1일차 2번째 방문지 삭제해줘"는 ITEM_LEVEL DELETE입니다.
- "1일차 방문지 삭제해줘"처럼 대상을 특정하지 못하면 target_scope를 UNKNOWN으로 둡니다.
- 응답은 JSON만 출력하세요.
"""

CLASSIFIER_USER_PROMPT = """\
{history_context}\
여행자 선호 컨텍스트:
{request_context}

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
   - MOVE: 장소 순서/위치 이동. 출발 Day와 도착 Day가 달라도 MOVE로 분류

2. **Target Scope 분류**
   - ITEM: 장소 1개를 추가/삭제/교체/이동
   - DAY_PLACES: 두 일차의 places 배열만 서로 교체. day_number와 daily_date는 바꾸지 않음
   - DAY_OPTIMIZE: 단일 일차의 전체 장소 순서를 route optimization 정책으로 재배치
   - "1일차랑 2일차 일정 바꿔줘"는 op=REPLACE, target_scope=DAY_PLACES, target_day=1, destination_day=2
   - "1일차 전체 일정 최적화해줘"는 op=MOVE, target_scope=DAY_OPTIMIZE, target_day=1
   - 날짜, 기간, 숙박 수를 바꾸는 요청은 DAY_PLACES가 아닙니다.

3. **Entity Linking**
   - "점심", "저녁", "카페" 등 표현을 아래 매핑 테이블의 (day_number, visit_sequence)로 매핑하세요.
   - "거기", "아까 그거" 등 지시어는 대화 맥락(session_history)을 참고하여 해소하세요.

4. **Search Keyword 추출**
   - REPLACE/ADD 시 Google Places API Text Search(textQuery)에 직접 넣을 검색어를 작성하세요.
   - 단, target_scope=DAY_PLACES인 REPLACE는 search_keyword를 null로 설정하세요.
   - REMOVE/MOVE 시 search_keyword는 null로 설정하세요.
   - search_keyword 형식은 반드시 "<지역명 또는 동네> <장소명/장소유형>" 입니다.
   - search_keyword에는 target_day의 위치 기반 컨텍스트(지역명)를 반드시 포함하세요.
   - 예시: "서울 성수 브런치 카페", "도쿄 시부야 스시 오마카세"

5. **MOVE 이동 목적지**
   - MOVE 시 destination_day(이동 목적지 일자)와 destination_index(이동 목적지 순서)를 반드시 설정하세요.
   - 단, target_scope=DAY_OPTIMIZE인 MOVE는 destination_day와 destination_index를 null로 설정하세요.
   - "마지막으로"는 destination_index를 도착 일자의 마지막 다음 위치로 설정하세요.
   - "처음으로"는 destination_index=1로 설정하세요.
   - "점심 뒤로", "카페 다음으로"는 해당 anchor의 다음 visit_sequence로 설정하세요.
   - "점심 앞으로", "카페 전에"는 해당 anchor의 현재 visit_sequence로 설정하세요.
   - REPLACE/ADD/REMOVE 시 destination_day와 destination_index는 null로 설정하세요.
   - 단, target_scope=DAY_PLACES인 REPLACE는 destination_day를 설정하고 destination_index는 null로 설정하세요.
   - 단, needs_clarification=true라면 MOVE여도 destination_day와 destination_index는 null이어도 됩니다.

6. **복합 요청 처리**
   - 두 가지 이상의 수정이 감지되면 **첫 번째 요청만** 추출하세요.
   - is_compound를 true로 설정하세요.

7. **모호성 감지**
   - 대상을 특정할 수 없으면 needs_clarification을 true로 설정하세요.
   - anchor가 여러 개라 특정할 수 없으면 needs_clarification을 true로 설정하세요.
   - reasoning에 어떤 부분이 모호한지 구체적으로 작성하세요.
   - 예: "식당 바꿔줘" 인데 식당이 2곳 이상인 경우

## 현재 로드맵 매핑 테이블

{itinerary_table}

## 출력 형식

{format_instructions}
"""

MODIFICATION_USER_PROMPT = """\
{history_context}\
여행자 선호 컨텍스트:
{request_context}

Day별 위치 컨텍스트:
{day_region_context}

사용자 요청: {user_query}
"""


class ChatIntentRoute(BaseModel):
    """대화 라우팅 분류 결과."""

    intent_type: Literal["GENERAL_CHAT", "MODIFICATION"] = Field(..., description="의도 분류 결과")
    requested_action: Literal["DELETE", "ADD", "REPLACE", "MOVE", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="수정 요청 액션 분류",
    )
    target_scope: Literal["DAY_LEVEL", "DAY_PLACES", "DAY_OPTIMIZE", "ITEM_LEVEL", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="수정 대상 범위 분류",
    )
    reasoning: str = Field(default="", description="분류 근거")


class ChatIntentDraft(BaseModel):
    """수정 의도 초안 모델.

    파싱 실패를 줄이기 위해 최소 제약으로 먼저 파싱한다.
    """

    op: ChatOperation
    target_scope: Literal["ITEM", "DAY_PLACES", "DAY_OPTIMIZE"] = "ITEM"
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


def _build_request_context(request_context: dict) -> str:
    """요청 기반 선호 정보를 프롬프트 컨텍스트 문자열로 변환합니다."""
    if not request_context:
        return "(요청 기반 선호 정보 없음)"

    travel_themes = request_context.get("travel_themes") or []
    companion_types = request_context.get("companion_type") or []
    companion_types_text = ", ".join([str(companion) for companion in companion_types]) if companion_types else "없음"
    travel_themes_text = ", ".join([str(theme) for theme in travel_themes]) if travel_themes else "없음"

    lines = [
        f"- companion_type: {companion_types_text}",
        f"- travel_themes: {travel_themes_text}",
        f"- pace_preference: {request_context.get('pace_preference', '없음')}",
        f"- planning_preference: {request_context.get('planning_preference', '없음')}",
        f"- destination_preference: {request_context.get('destination_preference', '없음')}",
        f"- activity_preference: {request_context.get('activity_preference', '없음')}",
        f"- priority_preference: {request_context.get('priority_preference', '없음')}",
    ]
    return "\n".join(lines)


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


def extract_region_hint_from_address(address: str) -> str | None:
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
            region_hint = extract_region_hint_from_address(str(place.get("address") or ""))
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
    if intent_draft.target_scope == "DAY_PLACES":
        return intent_draft.model_copy(update={"search_keyword": None})

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
        "최적화",
        "replace",
        "add",
        "remove",
        "move",
        "optimize",
        "reorder",
    )
    normalized = user_query.lower()
    return any(keyword in normalized for keyword in keywords)


def _has_day_optimize_keyword(user_query: str) -> bool:
    """동선 최적화 요청을 가리키는 핵심 키워드를 감지합니다."""
    text = (user_query or "").strip().lower()
    if not text:
        return False

    verb_tokens = (
        "최적화",
        "정리해줘",
        "재정렬",
        "줄여줘",
        "optimize",
        "reorder",
        "reduce",
    )
    target_tokens = (
        "동선",
        "이동거리",
        "일정",
        "코스",
        "동선 정리",
        "경로 정리",
        "route",
        "schedule",
        "itinerary",
    )
    return any(token in text for token in verb_tokens) and any(token in text for token in target_tokens)


def _is_global_day_optimize_request(user_query: str, itinerary: dict | None = None) -> bool:
    """전체 일정 또는 여러 일차를 한 번에 최적화하려는 요청을 감지합니다."""
    text = (user_query or "").strip().lower()
    if not _has_day_optimize_keyword(text):
        return False

    day_refs = _extract_day_references(text, itinerary)
    if len(day_refs) >= 2:
        return True

    global_tokens = (
        "전체 일정",
        "전 일정",
        "모든 일정",
        "전체 코스",
        "전체 동선",
        "여행 전체",
        "all days",
        "entire itinerary",
        "whole itinerary",
    )
    if not day_refs and any(token in text for token in global_tokens):
        return True

    return False


def _is_ambiguous_day_optimize_request(user_query: str, itinerary: dict | None = None) -> bool:
    """동선 최적화 의도는 있으나 대상 일차가 없는 요청을 감지합니다."""
    text = (user_query or "").strip().lower()
    if not _has_day_optimize_keyword(text):
        return False
    if _is_global_day_optimize_request(text, itinerary):
        return False
    return len(_extract_day_references(text, itinerary)) == 0


def _day_optimize_intent(user_query: str, itinerary: dict | None = None) -> ChatIntentDraft | None:
    """명확한 단일 일차 동선 최적화 요청을 LLM 없이 구조화합니다."""
    text = (user_query or "").strip()
    if not _has_day_optimize_keyword(text):
        return None
    if _is_global_day_optimize_request(text, itinerary) or _is_ambiguous_day_optimize_request(text, itinerary):
        return None

    day_refs = _extract_day_references(text, itinerary)
    if len(day_refs) != 1:
        return None

    return ChatIntentDraft(
        op=ChatOperation.MOVE,
        target_scope="DAY_OPTIMIZE",
        target_day=day_refs[0][0],
        target_index=1,
        destination_day=None,
        destination_index=None,
        search_keyword=None,
        reasoning="휴리스틱: 단일 일차 동선 최적화 요청",
    )


def _is_day_or_date_change_request(user_query: str) -> bool:
    """일차/날짜 자체 변경 요청을 휴리스틱으로 감지합니다."""
    text = (user_query or "").strip().lower()
    if not text:
        return False
    if _is_day_places_swap_request(text):
        return False

    day_tokens = (
        "일차를",
        "일정을 날짜",
        "날짜를",
        "여행 날짜",
        "trip day",
        "day를",
        "date를",
        "date ",
    )
    change_tokens = (
        "바꿔",
        "변경",
        "수정",
        "옮겨",
        "이동",
        "swap",
        "change",
        "move",
    )

    if any(day in text for day in day_tokens) and any(change in text for change in change_tokens):
        return True

    # "1일차를 2일차로 ..." 형태와 같이 day 번호 간 변경 요청을 추가 감지
    if re.search(r"\d+\s*일차", text) and "일차" in text and any(change in text for change in change_tokens):
        if ("에서" in text and "로" in text) or ("to" in text):
            return True

    return False


def _extract_day_numbers(user_query: str) -> list[int]:
    """사용자 요청에서 등장 순서대로 일차 번호를 추출합니다."""
    return [int(match) for match in re.findall(r"(\d+)\s*일차", user_query or "")]


def _extract_day_references(user_query: str, itinerary: dict | None = None) -> list[tuple[int, int]]:
    """사용자 요청에서 등장 순서대로 일차 참조를 추출합니다."""
    text = user_query or ""
    refs: list[tuple[int, int]] = []

    for match in re.finditer(r"(\d+)\s*일차", text):
        refs.append((int(match.group(1)), match.start()))

    for match in re.finditer(r"\bday\s*(\d+)\b", text, re.IGNORECASE):
        refs.append((int(match.group(1)), match.start()))

    total_days = len((itinerary or {}).get("itinerary", []))
    relative_patterns: list[tuple[re.Pattern[str], int | None]] = [
        (re.compile(r"첫\s*날|첫날|첫\s*번째\s*날|첫번째\s*날"), 1),
        (re.compile(r"마지막\s*날|마지막날|끝\s*날|끝날"), total_days or None),
    ]

    for pattern, default_day in relative_patterns:
        for match in pattern.finditer(text):
            if default_day is None:
                continue
            refs.append((default_day, match.start()))

    english_ordinals = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    for ordinal, day_number in english_ordinals.items():
        pattern = re.compile(rf"\b{ordinal}\s+day\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            refs.append((day_number, match.start()))

    if total_days:
        for match in re.finditer(r"\blast\s+day\b", text, re.IGNORECASE):
            refs.append((total_days, match.start()))

    refs.sort(key=lambda item: item[1])
    return refs


def _is_day_places_swap_request(user_query: str, itinerary: dict | None = None) -> bool:
    """날짜 변경이 아닌 두 일차의 장소 묶음 교체 요청을 감지합니다."""
    text = (user_query or "").strip().lower()
    if len(_extract_day_references(text, itinerary)) < 2:
        return False
    if any(token in text for token in ("날짜", "기간", "숙박", "시작일", "종료일")):
        return False
    if re.search(r"\d+\s*박(\s*\d+\s*일)?", text):
        return False
    swap_tokens = ("바꿔", "교체", "서로", "맞바꿔", "swap", "switch", "exchange")
    place_group_tokens = ("일정", "코스", "장소", "방문지", "places", "itinerary", "course")
    return any(token in text for token in swap_tokens) and any(token in text for token in place_group_tokens)


def _day_places_swap_intent(user_query: str, itinerary: dict | None = None) -> ChatIntentDraft | None:
    """명확한 일차 일정 묶음 교체 요청을 LLM 없이 구조화합니다."""
    if not _is_day_places_swap_request(user_query, itinerary):
        return None

    day_refs = _extract_day_references(user_query, itinerary)
    if len(day_refs) < 2:
        return None

    return ChatIntentDraft(
        op=ChatOperation.REPLACE,
        target_scope="DAY_PLACES",
        target_day=day_refs[0][0],
        target_index=1,
        destination_day=day_refs[1][0],
        destination_index=None,
        search_keyword=None,
        reasoning="휴리스틱: 두 일차의 장소 일정 묶음 교체 요청",
    )


def _parse_korean_position(text: str) -> int | str | None:
    """간단한 한국어 순서 표현을 1-based index 또는 anchor 문자열로 변환합니다."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return None
    if "마지막" in normalized or "끝" in normalized:
        return "LAST"
    if "처음" in normalized or "첫" in normalized:
        return 1

    match = re.search(r"(\d+)\s*(?:번|번째)", normalized)
    if match:
        return int(match.group(1))
    return None


def _find_day_place_count(itinerary: dict, day_number: int) -> int | None:
    """일차의 장소 개수를 반환합니다."""
    for day in itinerary.get("itinerary", []):
        if day.get("day_number") == day_number:
            return len(day.get("places", []))
    return None


def _simple_cross_day_move_intent(user_query: str, itinerary: dict) -> ChatIntentDraft | None:
    """명확한 "N일차 X번째 장소를 M일차 처음/마지막으로" 요청을 휴리스틱으로 구조화합니다."""
    text = (user_query or "").strip().lower()
    if not any(token in text for token in ("옮겨", "이동", "보내", "move")):
        return None

    day_refs = _extract_day_references(text, itinerary)
    if len(day_refs) < 2:
        return None

    source_day = day_refs[0][0]
    destination_day = day_refs[1][0]
    source_end = text.find("일차", day_refs[0][1]) + len("일차")
    destination_start = day_refs[1][1]
    source_phrase = text[source_end:destination_start]
    destination_phrase = text[destination_start:]
    source_index = _parse_korean_position(source_phrase)
    destination_index = _parse_korean_position(destination_phrase)

    if source_index == "LAST":
        source_count = _find_day_place_count(itinerary, source_day)
        if source_count is None:
            return None
        source_index = source_count
    if source_index is None:
        return None
    if destination_index == "LAST":
        destination_count = _find_day_place_count(itinerary, destination_day)
        if destination_count is None:
            return None
        destination_index = destination_count + 1
    if destination_index is None:
        return ChatIntentDraft(
            op=ChatOperation.MOVE,
            target_scope="ITEM",
            target_day=source_day,
            target_index=int(source_index),
            destination_day=destination_day,
            destination_index=None,
            search_keyword=None,
            reasoning="이동 목적지 위치가 모호합니다.",
            needs_clarification=True,
        )

    return ChatIntentDraft(
        op=ChatOperation.MOVE,
        target_scope="ITEM",
        target_day=source_day,
        target_index=int(source_index),
        destination_day=destination_day,
        destination_index=int(destination_index),
        search_keyword=None,
        reasoning="휴리스틱: 일차 간 장소 이동 요청",
    )


def _is_explicit_day_delete_request(user_query: str) -> bool:
    """일차 자체 삭제 요청을 휴리스틱으로 감지합니다."""
    text = (user_query or "").strip().lower()
    if not text:
        return False

    patterns = (
        r"\d+\s*일차\s*(전체|통째|자체)?\s*(를|은|는)?\s*(삭제|지워|빼줘|제거)",
        r"(day\s*\d+)\s*(전체|entire)?\s*(delete|remove|drop)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _is_ambiguous_day_item_delete_request(user_query: str) -> bool:
    """일차 내부 삭제 의도는 있으나 대상 장소 특정이 없는 요청을 감지합니다."""
    text = (user_query or "").strip().lower()
    if not text:
        return False

    day_ref = bool(re.search(r"\d+\s*일차", text)) or "day " in text or "day" in text
    has_delete = any(token in text for token in ("삭제", "지워", "빼줘", "제거", "remove", "delete", "drop"))
    if not (day_ref and has_delete):
        return False

    if _is_explicit_day_delete_request(text):
        return False

    has_item_word = any(token in text for token in ("장소", "방문지", "스팟", "place", "visit_sequence", "일정"))
    has_item_selector = bool(re.search(r"\d+\s*(번|번째)", text))
    return has_item_word and not has_item_selector


def _classify_intent_route(
    itinerary: dict,
    itinerary_table: str,
    history_context: str,
    request_context: str,
    user_query: str,
) -> ChatIntentRoute:
    """요청을 라우팅 스키마(GENERAL_CHAT/MODIFICATION + 상세 분류)로 분류합니다."""
    parser = PydanticOutputParser(pydantic_object=ChatIntentRoute)
    prompt = ChatPromptTemplate.from_messages([("system", CLASSIFIER_SYSTEM_PROMPT), ("human", CLASSIFIER_USER_PROMPT)])
    messages = prompt.format_messages(
        itinerary_table=itinerary_table,
        history_context=history_context,
        request_context=request_context,
        user_query=user_query,
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = invoke(Stage.CHAT_INTENT_ROUTING, messages)
        content = strip_code_fence(response.content)
        return parser.parse(content)
    except Exception as exc:
        logger.warning("의도 분류 LLM 호출 실패, 휴리스틱으로 대체: %s", exc)
        if _day_optimize_intent(user_query, itinerary):
            return ChatIntentRoute(
                intent_type="MODIFICATION",
                requested_action="MOVE",
                target_scope="DAY_OPTIMIZE",
                reasoning="휴리스틱: 단일 일차 동선 최적화 요청",
            )
        if _is_day_places_swap_request(user_query):
            return ChatIntentRoute(
                intent_type="MODIFICATION",
                requested_action="REPLACE",
                target_scope="DAY_PLACES",
                reasoning="휴리스틱: 일차 일정 묶음 교체 요청",
            )
        if _is_day_or_date_change_request(user_query):
            return ChatIntentRoute(
                intent_type="MODIFICATION",
                requested_action="MOVE",
                target_scope="DAY_LEVEL",
                reasoning="휴리스틱: 일차/날짜 변경 요청",
            )
        if _is_explicit_day_delete_request(user_query):
            return ChatIntentRoute(
                intent_type="MODIFICATION",
                requested_action="DELETE",
                target_scope="DAY_LEVEL",
                reasoning="휴리스틱: 일차 단위 삭제 요청",
            )
        if _is_ambiguous_day_item_delete_request(user_query):
            return ChatIntentRoute(
                intent_type="MODIFICATION",
                requested_action="DELETE",
                target_scope="UNKNOWN",
                reasoning="휴리스틱: 삭제 대상이 모호한 요청",
            )
        if _has_modification_keyword(user_query):
            return ChatIntentRoute(intent_type="MODIFICATION", reasoning="휴리스틱: 수정 의도 키워드 감지")
        return ChatIntentRoute(intent_type="GENERAL_CHAT", reasoning="휴리스틱: 일반 대화")


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
    request_context: str,
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
        request_context=request_context,
        day_region_context=day_region_context,
        user_query=user_query,
    )

    response = invoke(Stage.CHAT_INTENT_STRUCTURING, messages)
    content = strip_code_fence(response.content)

    try:
        return parser.parse(content)
    except Exception as exc:
        recovered = _extract_json_object(content)
        if recovered is not None:
            return ChatIntentDraft.model_validate(recovered)
        raise ValueError("수정 의도 응답 파싱에 실패했습니다.") from exc


def _emit_intent_event(event_type: str, severity: str, status: str, message: str, extra_fields: list[dict]) -> None:
    schedule_webhook(
        notify_pipeline_event(
            event_type=event_type,
            severity=severity,
            stage="chat.intent",
            status=status,
            title="🧭 Intent Analysis Stage",
            message=message,
            extra_fields=extra_fields,
        )
    )


def analyze_intent(state: ChatState) -> ChatState:
    """사용자 요청을 GENERAL_CHAT 또는 MODIFICATION으로 분류합니다."""
    current_itinerary = state.get("current_itinerary")
    user_query = state.get("user_query")
    session_history = state.get("session_history", [])
    request_context = state.get("request_context", {})

    if not current_itinerary or not user_query:
        return {**state, "error": "의도 분석에는 current_itinerary와 user_query가 필요합니다."}

    itinerary_table = _build_itinerary_table(current_itinerary)
    history_context = _build_history_context(session_history)
    request_context_text = _build_request_context(request_context)
    day_region_hints = _build_day_region_hints(current_itinerary)
    day_region_context = _format_day_region_context(day_region_hints)

    route = _classify_intent_route(
        current_itinerary, itinerary_table, history_context, request_context_text, user_query
    )
    append_job_log(
        "analyze_intent",
        f"type={route.intent_type} action={route.requested_action} scope={route.target_scope}",
    )
    day_optimize_intent = _day_optimize_intent(user_query, current_itinerary)
    day_places_swap_intent = _day_places_swap_intent(user_query, current_itinerary)
    simple_cross_day_move_intent = _simple_cross_day_move_intent(user_query, current_itinerary)
    has_heuristic_modification_signal = any(
        (
            day_optimize_intent is not None,
            day_places_swap_intent is not None,
            simple_cross_day_move_intent is not None,
            _is_global_day_optimize_request(user_query, current_itinerary),
            _is_ambiguous_day_optimize_request(user_query, current_itinerary),
            _is_day_or_date_change_request(user_query),
            _is_explicit_day_delete_request(user_query),
            _is_ambiguous_day_item_delete_request(user_query),
        )
    )

    if route.intent_type == "GENERAL_CHAT" and not has_heuristic_modification_signal:
        return {**state, "intent_type": "GENERAL_CHAT"}

    if route.requested_action == "DELETE" and route.target_scope == "DAY_LEVEL":
        _emit_intent_event(
            "chat_intent_rejected",
            "warning",
            "REJECTED",
            "일차 삭제 요청이 거부되었습니다.",
            [{"name": "Reason", "value": "일차 삭제는 지원하지 않습니다.", "inline": False}],
        )
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.REJECTED,
            "change_summary": "일차 삭제는 지원하지 않습니다. 삭제할 장소 순서를 지정해 주세요.",
        }

    if route.requested_action == "DELETE" and route.target_scope == "UNKNOWN":
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.ASK_CLARIFICATION,
            "change_summary": "삭제할 일차와 장소 순서를 함께 알려주세요. 예: '1일차 2번째 장소 삭제해줘'",
        }

    if _is_global_day_optimize_request(user_query, current_itinerary):
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.REJECTED,
            "change_summary": (
                "여러 일차나 전체 일정 동선 최적화는 아직 지원하지 않습니다. 최적화할 한 개의 일차를 지정해 주세요."
            ),
        }

    if _is_ambiguous_day_optimize_request(user_query, current_itinerary):
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.ASK_CLARIFICATION,
            "change_summary": "동선을 최적화할 일차를 알려주세요. 예: '1일차 전체 일정 최적화해줘'",
        }

    if _is_day_or_date_change_request(user_query):
        _emit_intent_event(
            "chat_intent_rejected",
            "warning",
            "REJECTED",
            "일차 변경 요청이 거부되었습니다.",
            [
                {
                    "name": "Reason",
                    "value": "여행 날짜, 기간, 숙박 수 변경은 전체 일정 재구성이 필요합니다.",
                    "inline": False,
                }
            ],
        )
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.REJECTED,
            "change_summary": "여행 날짜, 기간, 숙박 수 변경은 전체 일정 재구성이 필요합니다.",
        }

    if route.target_scope == "DAY_LEVEL" and not (day_places_swap_intent or simple_cross_day_move_intent):
        _emit_intent_event(
            "chat_intent_rejected",
            "warning",
            "REJECTED",
            "일차 변경 요청이 거부되었습니다.",
            [{"name": "Reason", "value": "일차 자체는 변경할 수 없습니다.", "inline": False}],
        )
        return {
            **state,
            "intent_type": "MODIFICATION",
            "status": ChatStatus.REJECTED,
            "change_summary": "일차(날짜) 자체는 변경할 수 없습니다. 각 일차에 배치된 장소 일정만 수정할 수 있어요.",
        }

    try:
        intent_draft = day_optimize_intent or day_places_swap_intent or simple_cross_day_move_intent
        if intent_draft is None:
            intent_draft = _parse_modification_intent(
                itinerary_table=itinerary_table,
                history_context=history_context,
                request_context=request_context_text,
                day_region_context=day_region_context,
                user_query=user_query,
            )
        intent_draft = _ensure_search_keyword_contains_region(intent_draft, day_region_hints)
        append_job_log(
            "intent_parsed",
            f"op={intent_draft.op} day={intent_draft.target_day} idx={intent_draft.target_index}"
            f" kw={intent_draft.search_keyword[:30] if intent_draft.search_keyword else 'N/A'}"
            f" clarify={intent_draft.needs_clarification}",
            level="detail",
        )
    except Exception as exc:
        logger.error("의도 분석 LLM 호출 실패: %s", exc)
        _emit_intent_event(
            "chat_intent_failed",
            "error",
            "FAILED",
            "수정 의도 분석에 실패했습니다.",
            [{"name": "Error", "value": type(exc).__name__, "inline": False}],
        )
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
