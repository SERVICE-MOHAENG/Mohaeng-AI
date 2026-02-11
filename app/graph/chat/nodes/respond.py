"""수정 결과 자연어 응답 생성 LLM 노드."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import get_logger
from app.graph.chat.llm import get_llm
from app.graph.chat.state import ChatState
from app.schemas.enums import ChatStatus

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
당신은 친절하고 전문적인 여행 가이드입니다.
로드맵 수정 결과를 사용자에게 자연어로 안내하세요.

## 톤
- 친근하지만 전문적
- 핵심 변경 사항을 먼저 전달
- 다른 일자에는 영향 없음을 명시

## 상태별 응답

### SUCCESS
- 무엇이 어떻게 바뀌었는지 구체적으로 설명
- 복합 요청이었다면 "나머지 요청도 이어서 처리할까요?" 안내

### ASK_CLARIFICATION
- 모호성 해소 질문 생성
- 검색 실패 시 대안 키워드 제안

### REJECTED
- 거부 사유를 명확히 설명

## 경고
- warnings가 있으면 자연어로 안내
- 이동 수단 변경은 제안만
"""

USER_PROMPT = """\
수정 상태: {status}
사용자 요청: {user_query}
변경 요약: {change_summary}
경고: {warnings}
복합 요청: {is_compound}
대안 키워드: {suggested_keyword}

위 정보를 바탕으로 사용자에게 전달할 응답을 작성하세요. 응답만 출력하세요.
"""


def respond(state: ChatState) -> ChatState:
    """수정 결과에 대한 자연어 응답을 생성합니다."""
    status = state.get("status", ChatStatus.SUCCESS)
    user_query = state.get("user_query", "")
    change_summary = state.get("change_summary", "")
    warnings = state.get("warnings", [])
    intent = state.get("intent", {})
    suggested_keyword = state.get("suggested_keyword")
    error = state.get("error")

    if error:
        # CodeRabbit 리뷰 반영: 내부 오류를 사용자에게 직접 노출하지 않음
        logger.warning("수정 그래프 내 오류 발생: %s", error)
        return {
            **state,
            "status": ChatStatus.REJECTED,
            "message": "요청을 처리하는 중 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        }

    is_compound = intent.get("is_compound", False)

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])
    messages = prompt.format_messages(
        status=status,
        user_query=user_query,
        change_summary=change_summary,
        warnings="\n".join(warnings) if warnings else "없음",
        is_compound=str(is_compound),
        suggested_keyword=suggested_keyword or "없음",
    )

    try:
        response = get_llm().invoke(messages)
        generated = response.content.strip()
    except Exception as exc:
        logger.error("응답 생성 LLM 호출 실패: %s", exc)
        generated = change_summary or "수정 처리 중 오류가 발생했습니다."

    final_status = status if status else ChatStatus.SUCCESS

    return {**state, "status": final_status, "message": generated}
