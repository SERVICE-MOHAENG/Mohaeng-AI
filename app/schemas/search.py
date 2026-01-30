from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """검색 API에 대한 요청 본문(body) 모델.

    Attributes:
        query (str): 사용자가 검색할 자연어 텍스트. 최소 1자 이상이어야 합니다.
        top_k (int): 반환받을 추천 지역의 최대 개수. 1에서 20 사이의 값.
    """

    query: str = Field(..., min_length=1, description="검색할 자연어 텍스트 (최소 1자 이상)")
    top_k: int = Field(default=3, ge=1, le=20, description="추천받을 지역의 수")


class RegionRecommendation(BaseModel):
    """지역 추천 결과의 개별 항목 모델.

    AI DB에는 최소한의 정보만 저장하므로, region_id를 통해
    백엔드 MySQL DB에서 상세 정보를 조회해야 합니다.
    """

    region_id: UUID | None = Field(None, description="백엔드 region 테이블의 ID")
    region_name: str = Field(..., description="지역명 (백엔드 연동 전 임시 식별용)")


class SearchResponse(BaseModel):
    """검색 API 응답 모델."""

    query: str = Field(..., description="사용자가 입력한 검색 쿼리")
    results: list[RegionRecommendation] = Field(..., description="추천 지역 목록")
