"""로드맵 수정 요청/응답 스키마."""

from pydantic import BaseModel, Field

from app.schemas.course import CourseResponse
from app.schemas.enums import ModifyOperation, ModifyStatus


class Message(BaseModel):
    """대화 메시지 모델."""

    role: str = Field(..., description="메시지 역할 (user / assistant)")
    content: str = Field(..., description="메시지 내용")


class ModifyMetadata(BaseModel):
    """수정 요청 부가 메타데이터."""

    latitude: float | None = Field(default=None, description="사용자 현재 위도")
    longitude: float | None = Field(default=None, description="사용자 현재 경도")
    preferred_categories: list[str] = Field(default_factory=list, description="선호 카테고리 목록")


class ModifyRequest(BaseModel):
    """로드맵 수정 요청 모델.

    Fields:
        current_itinerary: 현재 세션의 전체 로드맵
        user_query: 사용자 수정 요청 발화
        session_history: 최근 3~5건 대화 맥락 (지시어 해소용)
        metadata: 사용자 위치, 선호 카테고리 등
    """

    current_itinerary: CourseResponse = Field(..., description="현재 세션의 전체 로드맵 데이터")
    user_query: str = Field(..., min_length=1, description="사용자 수정 요청 발화")
    session_history: list[Message] = Field(default_factory=list, description="최근 대화 맥락")
    metadata: ModifyMetadata | None = Field(default=None, description="부가 메타데이터")


class ModifyIntent(BaseModel):
    """LLM이 추출한 수정 의도 모델."""

    op: ModifyOperation = Field(..., description="수정 Operation (REPLACE / ADD / REMOVE / MOVE)")
    target_day: int = Field(..., ge=1, description="대상 일자 (1-based)")
    target_index: int = Field(..., ge=1, description="대상 visit_sequence (1-based)")
    search_keyword: str | None = Field(default=None, description="REPLACE/ADD 시 검색 키워드")
    reasoning: str = Field(..., description="해당 인덱스를 선택한 근거")
    is_compound: bool = Field(default=False, description="복합 요청 여부 (True 시 첫 번째만 처리)")


class ModifyResponse(BaseModel):
    """로드맵 수정 응답 모델.

    Fields:
        status: 수정 결과 상태
        modified_itinerary: 수정 완료된 로드맵 (SUCCESS 시)
        change_summary: 변경 사항 자연어 피드백
        diff_keys: UI 하이라이트용 수정 노드 ID 리스트
        clarification_question: 모호성 해소 질문 (ASK_CLARIFICATION 시)
        warnings: 경고 메시지 목록
        suggested_keyword: 검색 실패 시 대안 키워드 제안
    """

    status: ModifyStatus = Field(..., description="수정 결과 상태")
    modified_itinerary: CourseResponse | None = Field(default=None, description="수정 완료된 로드맵")
    change_summary: str = Field(default="", description="변경 사항 자연어 피드백")
    diff_keys: list[str] = Field(default_factory=list, description="수정된 노드 ID 리스트")
    clarification_question: str | None = Field(default=None, description="모호성 해소 질문")
    warnings: list[str] = Field(default_factory=list, description="경고 메시지 목록")
    suggested_keyword: str | None = Field(default=None, description="검색 실패 시 대안 키워드")
