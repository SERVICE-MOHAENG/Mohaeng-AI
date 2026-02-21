"""대화(Chat) 요청/응답 스키마."""

from datetime import date

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.schemas.course import DailyItinerary
from app.schemas.enums import (
    ActivityPreference,
    BudgetRange,
    ChatOperation,
    ChatStatus,
    CompanionType,
    DestinationPreference,
    PacePreference,
    PlanningPreference,
    PriorityPreference,
    TravelTheme,
)


class Message(BaseModel):
    """대화 메시지 모델."""

    role: str = Field(..., description="메시지 역할 (user / assistant)")
    content: str = Field(..., description="메시지 내용")


class ChatRoadmap(BaseModel):
    """대화 기능에서 사용하는 여행 로드맵 모델."""

    model_config = ConfigDict(extra="ignore")

    start_date: date = Field(..., description="여행 시작일")
    end_date: date = Field(..., description="여행 종료일")
    trip_days: int = Field(..., description="총 여행 일수")
    nights: int = Field(..., description="총 숙박 수")
    people_count: int = Field(..., description="총 인원 수")
    tags: list[str] = Field(..., description="여행 전체의 특징을 나타내는 태그 목록")
    title: str = Field(..., description="여행 로드맵의 제목")
    summary: str = Field(..., description="로드맵 한 줄 설명")
    planning_preference: PlanningPreference = Field(..., description="여행 계획 성향")
    itinerary: list[DailyItinerary] = Field(..., description="일자별 상세 일정 리스트")


class ChatRequest(BaseModel):
    """로드맵 대화 요청 모델.

    Fields:
        job_id: NestJS BullMQ job id
        callback_url: NestJS 콜백 URL
        current_itinerary: 현재 세션의 전체 로드맵
        companion_type: 동행자 유형
        travel_themes: 여행 테마 목록
        pace_preference: 일정 밀도 선호
        planning_preference: 여행 계획 성향
        destination_preference: 여행지 선호
        activity_preference: 활동 선호
        priority_preference: 우선 가치 선호
        budget_range: 예산 범위
        user_query: 사용자 수정 요청 발화
        session_history: 최근 3~5건 대화 맥락 (지시어 해소용)
    """

    model_config = ConfigDict(extra="ignore")

    job_id: str = Field(..., description="NestJS BullMQ job id")
    callback_url: AnyHttpUrl = Field(..., description="NestJS 콜백 URL")
    current_itinerary: ChatRoadmap = Field(..., description="현재 세션의 전체 로드맵 데이터")
    companion_type: CompanionType = Field(..., description="동행자 유형")
    travel_themes: list[TravelTheme] = Field(..., min_length=1, description="여행 테마 목록")
    pace_preference: PacePreference = Field(..., description="일정 밀도 선호")
    planning_preference: PlanningPreference = Field(..., description="여행 계획 성향")
    destination_preference: DestinationPreference = Field(..., description="여행지 선호")
    activity_preference: ActivityPreference = Field(..., description="활동 선호")
    priority_preference: PriorityPreference = Field(..., description="우선 가치 선호")
    budget_range: BudgetRange = Field(..., description="예산 범위")
    user_query: str = Field(..., min_length=1, description="사용자 수정 요청 발화")
    session_history: list[Message] = Field(default_factory=list, description="최근 대화 맥락")


class ChatAckResponse(BaseModel):
    """/api/v1/chat 비동기 처리 수락 응답."""

    job_id: str = Field(..., description="NestJS BullMQ job id")
    status: str = Field("ACCEPTED", description="요청 수락 상태")


class ChatIntent(BaseModel):
    """LLM이 추출한 수정 의도 모델."""

    op: ChatOperation = Field(..., description="수정 Operation (REPLACE / ADD / REMOVE / MOVE)")
    target_day: int = Field(..., ge=1, description="대상 일자 (1-based)")
    target_index: int = Field(..., ge=1, description="대상 visit_sequence (1-based)")
    destination_day: int | None = Field(default=None, ge=1, description="이동 목적지 일자 (MOVE 시 필수, 1-based)")
    destination_index: int | None = Field(
        default=None, ge=1, description="이동 목적지 visit_sequence (MOVE 시 필수, 1-based)"
    )
    search_keyword: str | None = Field(default=None, description="REPLACE/ADD 시 검색 키워드")
    reasoning: str = Field(..., description="해당 인덱스를 선택한 근거")
    is_compound: bool = Field(default=False, description="복합 요청 여부 (True 시 첫 번째만 처리)")
    needs_clarification: bool = Field(default=False, description="대상 특정 불가 시 True")

    @model_validator(mode="after")
    def validate_move_destination(self):
        """MOVE 시 destination_day, destination_index 필수 검증.

        모호성 해소가 필요한 경우(needs_clarification=True)에는
        목적지 값 누락을 허용해 ASK_CLARIFICATION 경로로 보낸다.
        """
        if self.needs_clarification:
            return self
        if self.op == ChatOperation.MOVE:
            if self.destination_day is None or self.destination_index is None:
                raise ValueError("MOVE 시 destination_day와 destination_index가 필요합니다.")
        return self


class ChatResponse(BaseModel):
    """로드맵 대화 응답 모델.

    Fields:
        status: 수정 결과 상태
        modified_itinerary: 수정 완료된 로드맵 (SUCCESS 시)
        message: 사용자에게 전달할 단일 응답 메시지
        diff_keys: UI 하이라이트용 수정 노드 ID 리스트
    """

    status: ChatStatus = Field(..., description="수정 결과 상태")
    modified_itinerary: ChatRoadmap | None = Field(default=None, description="수정 완료된 로드맵")
    message: str = Field(default="", description="사용자에게 전달할 단일 응답 메시지")
    diff_keys: list[str] = Field(default_factory=list, description="수정된 노드 ID 리스트")
