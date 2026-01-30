from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """검색 API에 대한 요청 본문(body) 모델.

    Attributes:
        query (str): 사용자가 검색할 자연어 텍스트. 최소 1자 이상이어야 합니다.
        top_k (int): 반환받을 추천 도시의 최대 개수. 1에서 20 사이의 값.
    """

    query: str = Field(..., min_length=1, description="검색할 자연어 텍스트 (최소 1자 이상)")
    top_k: int = Field(default=3, ge=1, le=20, description="추천받을 도시의 수")


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
