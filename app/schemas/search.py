from pydantic import BaseModel, Field


class CityRecommendation(BaseModel):
    """도시 추천 결과의 개별 항목 모델."""

    city: str = Field(..., description="도시 이름")
    country: str = Field(..., description="국가 이름")
    description: str = Field(..., description="도시 설명 (최대 150자)")
    reason: str = Field(..., description="추천 사유")


class SearchResponse(BaseModel):
    """검색 API 응답 모델."""

    query: str = Field(..., description="사용자가 입력한 검색 쿼리")
    results: list[CityRecommendation] = Field(..., description="추천 도시 목록")
