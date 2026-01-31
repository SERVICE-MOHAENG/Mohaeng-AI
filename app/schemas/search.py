"""검색 API 스키마."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """검색 API 요청 모델."""

    query: str = Field(..., min_length=1, description="검색할 자연어 텍스트")
    top_k: int = Field(default=3, ge=1, le=20, description="추천받을 지역의 수")


class RegionRecommendation(BaseModel):
    """지역 추천 결과 항목 모델."""

    region_id: UUID | None = Field(None, description="백엔드 region 테이블의 ID")
    region_name: str = Field(..., description="지역명")


class SearchResponse(BaseModel):
    """검색 API 응답 모델."""

    query: str = Field(..., description="사용자가 입력한 검색 쿼리")
    results: list[RegionRecommendation] = Field(..., description="추천 지역 목록")


class UserPreferenceRequest(BaseModel):
    """사용자 선호도 기반 추천 요청 모델."""

    travel_range: str | None = Field(None, description="여행 거리 (DOMESTIC, NEAR_ASIA, EUROPE 등)")
    budget_level: str | None = Field(None, description="예산 수준 (LOW, MEDIUM, HIGH, VERY_HIGH)")
    main_interests: list[str] | None = Field(None, description="관심사 (HISTORY, NATURE, FOOD 등)")
    environment: str | None = Field(None, description="환경 선호 (URBAN, NATURE, COASTAL, MOUNTAIN)")
    weather: str | None = Field(None, description="날씨 선호 (WARM, COOL, TROPICAL)")
    top_k: int = Field(default=3, ge=1, le=20, description="추천받을 지역의 수")


class RecommendationResult(BaseModel):
    """추천 결과 항목 모델 (추천 사유 포함)."""

    region_id: UUID | None = Field(None, description="백엔드 region 테이블의 ID")
    region_name: str = Field(..., description="지역명")
    score: float = Field(..., description="추천 점수")
    reason: str = Field(..., description="AI 추천 사유")


class RecommendResponse(BaseModel):
    """추천 API 응답 모델."""

    results: list[RecommendationResult] = Field(..., description="추천 지역 목록")
