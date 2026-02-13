"""로드맵 대화 그래프 상태 정의."""

from typing import TypedDict


class ChatState(TypedDict, total=False):
    """로드맵 대화 그래프 상태.

    Keys:
        current_itinerary: 현재 로드맵 데이터
        user_query: 사용자 수정 요청 발화
        session_history: 최근 대화 맥락
        request_context: 요청 기반 여행 선호 컨텍스트
        intent_type: 분류기 결과 (GENERAL_CHAT / MODIFICATION)
        intent: LLM이 추출한 수정 의도
        search_results: Google Places 검색 결과
        warnings: 경고 메시지 누적
        visit_time_proposals: 일자별 visit_sequence 기반 시각 제안
        modified_itinerary: 수정 완료된 로드맵
        status: 수정 결과 상태
        change_summary: 변경 사항 자연어 피드백
        message: 사용자 전달용 최종 메시지
        diff_keys: 수정된 노드 ID 리스트
        suggested_keyword: 검색 실패 시 대안 키워드
        error: 오류 메시지
    """

    # Input
    current_itinerary: dict
    user_query: str
    session_history: list[dict]
    request_context: dict

    # Processing
    intent_type: str
    intent: dict
    search_results: list
    warnings: list[str]
    visit_time_proposals: dict[int, dict[int, str]]

    # Output
    modified_itinerary: dict | None
    status: str
    change_summary: str
    message: str
    diff_keys: list[str]
    suggested_keyword: str | None
    error: str | None
