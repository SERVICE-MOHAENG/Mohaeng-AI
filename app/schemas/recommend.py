"""설문 기반 추천 워커 API 스키마."""

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

Weather = Literal["OCEAN_BEACH", "SNOW_HOT_SPRING", "CLEAN_CITY_BREEZE", "INDOOR_LANDMARK"]
TravelRange = Literal["SHORT_HAUL", "MEDIUM_HAUL", "LONG_HAUL"]
TravelStyle = Literal["MODERN_TRENDY", "HISTORIC_RELAXED", "PURE_NATURE"]
BudgetLevel = Literal["COST_EFFECTIVE", "BALANCED", "PREMIUM_LUXURY"]
FoodPersonality = Literal["LOCAL_HIDDEN_GEM", "FINE_DINING", "INSTAGRAMMABLE"]
MainInterest = Literal["SHOPPING_TOUR", "DYNAMIC_ACTIVITY", "ART_AND_CULTURE"]


class SurveyPreference(BaseModel):
    """추천 로직에서 사용하는 설문 응답 모델."""

    weather: Weather | None = Field(default=None, description="선호 날씨")
    travel_range: TravelRange | None = Field(default=None, description="여행 거리 선호")
    travel_style: TravelStyle | None = Field(default=None, description="여행 스타일")
    budget_level: BudgetLevel | None = Field(default=None, description="예산 선호")
    food_personality: list[FoodPersonality] | None = Field(default=None, description="음식 성향")
    main_interests: list[MainInterest] | None = Field(default=None, description="주요 관심사")


class RecommendRequest(BaseModel):
    """NestJS에서 추천 작업을 트리거할 때 사용하는 요청 본문."""

    job_id: str = Field(..., description="BullMQ 작업 ID")
    callback_url: AnyHttpUrl = Field(..., description="NestJS 콜백 베이스 URL")
    weather: Weather | None = Field(default=None, description="선호 날씨")
    travel_range: TravelRange | None = Field(default=None, description="여행 거리 선호")
    travel_style: TravelStyle | None = Field(default=None, description="여행 스타일")
    budget_level: BudgetLevel | None = Field(default=None, description="예산 선호")
    food_personality: list[FoodPersonality] | None = Field(default=None, description="음식 성향")
    main_interests: list[MainInterest] | None = Field(default=None, description="주요 관심사")

    def to_survey(self) -> SurveyPreference:
        return SurveyPreference(
            weather=self.weather,
            travel_range=self.travel_range,
            travel_style=self.travel_style,
            budget_level=self.budget_level,
            food_personality=self.food_personality,
            main_interests=self.main_interests,
        )


class RecommendAckResponse(BaseModel):
    """비동기 처리 접수 즉시 반환하는 ACK 응답."""

    job_id: str = Field(..., description="접수된 작업 ID")
    status: str = Field(default="ACCEPTED", description="요청 상태")


class RecommendedDestination(BaseModel):
    """추천 여행지 단일 항목."""

    region_name: str = Field(..., description="추천 지역명")


class RecommendResultData(BaseModel):
    """추천 성공 시 콜백으로 전달되는 데이터 본문."""

    analysis_summary: str = Field(..., description="사용자 성향 한 줄 요약")
    recommended_destinations: list[RecommendedDestination] = Field(
        ..., min_length=5, max_length=5, description="정확히 5개의 추천 여행지"
    )


class CallbackError(BaseModel):
    """FAILED 콜백에 사용되는 오류 정보."""

    code: str = Field(..., description="오류 코드")
    message: str = Field(..., description="오류 메시지")


class RecommendCallbackSuccess(BaseModel):
    """성공 콜백 페이로드."""

    status: Literal["SUCCESS"] = Field(default="SUCCESS", description="작업 결과 상태")
    data: RecommendResultData = Field(..., description="추천 결과 데이터")


class RecommendCallbackFailure(BaseModel):
    """실패 콜백 페이로드."""

    status: Literal["FAILED"] = Field(default="FAILED", description="작업 결과 상태")
    error: CallbackError = Field(..., description="실패 상세 정보")
