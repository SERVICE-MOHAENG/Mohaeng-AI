"""API 엔드포인트 정의."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.database import get_db
from app.graph.workflow import compiled_graph
from app.schemas.search import (
    RecommendationResult,
    RecommendResponse,
    RegionRecommendation,
    SearchRequest,
    SearchResponse,
    UserPreferenceRequest,
)
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


@router.post("/recommend", response_model=RecommendResponse)
def recommend_regions(request: UserPreferenceRequest, db: Session = Depends(get_db)) -> RecommendResponse:  # noqa: B008
    """사용자 선호도를 기반으로 `LangGraph` 워크플로우를 실행하여 지역을 추천합니다."""
    logger.info("Recommend request received: %s", request.model_dump())

    initial_state = {
        "user_preference": {
            "travel_range": request.travel_range,
            "budget_level": request.budget_level,
            "main_interests": request.main_interests or [],
            "environment": request.environment,
            "weather": request.weather,
        },
        "top_k": request.top_k,
    }

    try:
        result = compiled_graph.invoke(initial_state, config={"configurable": {"db": db}})

        if error := result.get("error"):
            raise HTTPException(status_code=500, detail=error)

        final_recommendations = result.get("final_recommendations", [])

        recommendations = [
            RecommendationResult(
                region_id=r["region_id"],
                region_name=r["region_name"],
                score=r["score"],
                reason=r["reason"],
            )
            for r in final_recommendations
        ]

        logger.info("Recommend completed: %d regions", len(recommendations))

        return RecommendResponse(results=recommendations)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Recommend failed: %s", e)
        raise HTTPException(status_code=500, detail="추천 처리 중 오류가 발생했습니다") from e
