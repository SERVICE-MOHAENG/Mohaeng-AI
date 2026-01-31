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
