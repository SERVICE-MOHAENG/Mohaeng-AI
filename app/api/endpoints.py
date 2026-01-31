"""API 엔드포인트 정의."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.database import get_db
from app.schemas.search import RegionRecommendation, SearchRequest, SearchResponse
from app.services.embedding import EmbeddingService
from app.services.region_service import search_regions_by_vector

router = APIRouter(tags=["search"])
logger = get_logger(__name__)

embedder = EmbeddingService()


@router.post("/search", response_model=SearchResponse)
def search_regions(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:  # noqa: B008
    """사용자 쿼리를 기반으로 의미상 가장 유사한 지역 목록을 반환합니다."""
    logger.info("Search request received: query=%s", request.query)

    query_vector = embedder.get_embedding(request.query)
    if not query_vector:
        raise HTTPException(status_code=500, detail="임베딩 생성 실패")

    results = search_regions_by_vector(db, query_vector, request.top_k)
    logger.info("Search completed: %d regions found", len(results))

    recommendations = [
        RegionRecommendation(
            region_id=region.region_id,
            region_name=region.region_name,
        )
        for region in results
    ]

    return SearchResponse(query=request.query, results=recommendations)
