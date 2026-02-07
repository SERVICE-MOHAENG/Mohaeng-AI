"""여행 코스 요청/응답 스키마."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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


class RegionDateRange(BaseModel):
    """지역별 여행 기간 모델."""

    region: Region = Field(..., description="여행 지역")
    start_date: date = Field(..., description="지역별 여행 시작일 (YYYY-MM-DD)")
    end_date: date = Field(..., description="지역별 여행 종료일 (YYYY-MM-DD)")

    @field_validator("end_date")
    @classmethod
    def validate_region_date_range(cls, value: date, info):
        start_date = info.data.get("start_date")
        if start_date and value < start_date:
            raise ValueError("지역별 여행 종료일은 시작일과 같거나 이후여야 합니다.")
        return value


class CourseRequest(BaseModel):
    """여행 코스 생성 요청 모델.

    Fields:
        `regions`: 지역별 여행 기간
        `start_date`: 전체 여행 시작일
        `end_date`: 전체 여행 종료일
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

    start_date: date = Field(..., description="여행 시작일 (YYYY-MM-DD)")
    end_date: date = Field(..., description="여행 종료일 (YYYY-MM-DD)")
    regions: List[RegionDateRange] = Field(..., min_length=1, description="지역별 여행 기간")
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

    @model_validator(mode="after")
    def validate_regions_within_range(self):
        for region_range in self.regions:
            if region_range.start_date < self.start_date or region_range.end_date > self.end_date:
                raise ValueError("지역별 여행 기간은 전체 여행 기간 안에 있어야 합니다.")
        return self


class CoursePlace(BaseModel):
    """최하단 단위: 개별 방문 장소 모델."""

    place_name: str = Field(..., description="장소의 공식 명칭 (Google Places API 기준)")
    place_id: Optional[str] = Field(None, description="Google Places ID (상세 정보 조회용)")
    address: Optional[str] = Field(None, description="장소 주소")
    latitude: Optional[float] = Field(None, description="위도")
    longitude: Optional[float] = Field(None, description="경도")
    place_url: Optional[str] = Field(None, description="구글 맵 URL")
    description: str = Field(..., description="장소에 대한 한 줄 설명")
    visit_sequence: int = Field(..., ge=1, description="해당 일자 내 방문 순서 (1부터 시작)")
    visit_time: str = Field(..., description="방문 시점 (예: 오전, 10:00 AM, 12:30 PM)")


class DailyItinerary(BaseModel):
    """중간 단위: 일차별 일정 모델."""

    day_number: int = Field(..., ge=1, description="여행 N일차 (1, 2, 3...)")
    daily_date: date = Field(..., description="여행 날짜 (YYYY-MM-DD 형식)")
    places: List[CoursePlace] = Field(..., description="순서대로 정렬된 방문 장소 리스트")


class CourseResponse(BaseModel):
    """최종 여행 로드맵 응답 모델."""

    # 여행 메타데이터
    start_date: date = Field(..., description="여행 시작일")
    end_date: date = Field(..., description="여행 종료일")
    trip_days: int = Field(..., description="총 여행 일수")
    nights: int = Field(..., description="총 숙박 수")
    people_count: int = Field(..., description="총 인원 수")
    tags: list[str] = Field(..., description="여행 전체의 특징을 나타내는 태그 목록")

    # AI 생성 컨텐츠
    title: str = Field(..., description="여행 로드맵의 제목")
    summary: str = Field(..., description="로드맵 한 줄 설명")
    itinerary: List[DailyItinerary] = Field(..., description="일자별 상세 일정 리스트")
    llm_commentary: str = Field(..., description="코스 선정 이유 및 전체 흐름 설명")
    next_action_suggestion: list[str] = Field(..., description="사용자가 바로 입력할 수 있는 다음 행동 문장 목록")


class CourseResponseLLMOutput(BaseModel):
    """LLM이 생성할 필드만 포함하는 파싱 전용 모델."""

    title: str = Field(..., description="여행 로드맵의 제목")
    summary: str = Field(..., description="로드맵 한 줄 설명")
    tags: list[str] = Field(..., description="여행 전체를 요약하는 3~5개의 키워드 태그")
    llm_commentary: str = Field(..., description="코스 선정 이유 및 전체 흐름 설명")
    next_action_suggestion: list[str] = Field(..., description="사용자가 바로 입력할 수 있는 다음 행동 문장 목록")
