"""여행 코스 요청/응답 스키마."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import (
    ActivityPreference,
    BudgetRange,
    CompanionType,
    DestinationPreference,
    PacePreference,
    PlanningPreference,
    PriorityPreference,
    Region,
    TravelTheme,
)


class CourseRequest(BaseModel):
    """여행 코스 생성 요청 모델.

    Fields:
        `region`: 여행 지역
        `start_date`: 여행 시작일
        `end_date`: 여행 종료일
        `people_count`: 총 인원 수
        `companion_type`: 동행자 유형
        `travel_themes`: 여행 테마 목록
        `pace_preference`: 일정 밀도 선호
        `planning_preference`: 여행 계획 성향
        `destination_preference`: 여행지 선호
        `activity_preference`: 활동 선호
        `priority_preference`: 우선 가치 선호
        `budget_range`: 예산 범위
        `notes`: 추가 요청 사항
    """

    region: Region = Field(..., description="여행 지역")
    start_date: date = Field(..., description="여행 시작일 (YYYY-MM-DD)")
    end_date: date = Field(..., description="여행 종료일 (YYYY-MM-DD)")
    people_count: int = Field(..., ge=1, le=20, description="총 인원 수")
    companion_type: CompanionType = Field(..., description="동행자 유형")
    travel_themes: list[TravelTheme] = Field(..., min_length=1, description="여행 테마 목록")
    pace_preference: PacePreference = Field(..., description="일정 밀도 선호")
    planning_preference: PlanningPreference = Field(..., description="여행 계획 성향")
    destination_preference: DestinationPreference = Field(..., description="여행지 선호")
    activity_preference: ActivityPreference = Field(..., description="활동 선호")
    priority_preference: PriorityPreference = Field(..., description="우선 가치 선호")
    budget_range: BudgetRange = Field(..., description="예산 범위")
    notes: str | None = Field(default=None, description="추가 요청 사항")

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, value: date, info):
        start_date = info.data.get("start_date")
        if start_date and value < start_date:
            raise ValueError("여행 종료일은 시작일과 같거나 이후여야 합니다.")
        return value

    @field_validator("people_count")
    @classmethod
    def validate_people_count(cls, value: int):
        if value < 1:
            raise ValueError("인원 수는 1명 이상이어야 합니다.")
        return value


class CoursePlace(BaseModel):
    """최하위 단위: 개별 방문 장소 모델."""

    place_name: str = Field(..., description="장소의 공식 명칭 (Google Places API 기준)")
    place_id: Optional[str] = Field(None, description="Google Places ID (프론트엔드에서 상세 정보 조회용)")
    category: str = Field(..., description="장소 카테고리 (예: 식당, 관광지, 카페, 숙소)")
    visit_sequence: int = Field(..., ge=1, description="해당 일차 내에서의 방문 순서 (1부터 시작)")
    visit_time: str = Field(..., description="방문 시점 (예: 아침, 점심 or 10:00 AM, 12:30 PM 등)")


class DailyItinerary(BaseModel):
    """중간 단위: 일차별 일정 모델."""

    day_number: int = Field(..., ge=1, description="여행 N일차 (1, 2, 3...)")
    daily_date: date = Field(..., description="여행 날짜 (YYYY-MM-DD 형식)")
    places: List[CoursePlace] = Field(..., description="순서대로 정렬된 방문 장소 리스트")


class CourseResponse(BaseModel):
    """최종 여행 로드맵 응답 모델."""

    title: str = Field(..., description="여행 로드맵의 제목")
    itinerary: List[DailyItinerary] = Field(..., description="일자별 상세 일정 리스트")
    llm_commentary: str = Field(..., description="코스 선정 이유 및 전체 흐름 설명")
    next_action_suggestion: str = Field(..., description="사용자에게 제안할 다음 액션")
