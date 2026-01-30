import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.search import RegionRecommendation, SearchRequest, SearchResponse
from app.services.embedding import EmbeddingService
from app.services.region_service import search_regions_by_vector

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

# [권장] EmbeddingService를 모듈 로드 시점에 초기화하면,
# OPENAI_API_KEY가 설정되지 않았을 때 서버 시작과 동시에 실패하게 됩니다.
# 테스트 용이성 및 유연성을 위해 FastAPI의 의존성 주입 패턴 (Depends) 사용을 권장합니다.
# 예: def get_embedder(): return EmbeddingService()
#      @router.post("/search", embedder: EmbeddingService = Depends(get_embedder))
embedder = EmbeddingService()


@router.post("/search", response_model=SearchResponse)
def search_regions(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:  # noqa: B008
    """사용자 쿼리를 기반으로 의미상 가장 유사한 지역 목록을 반환합니다.

    이 엔드포인트는 다음 단계를 거칩니다:
    1. 요청 본문에서 받은 쿼리 텍스트를 임베딩 벡터로 변환합니다.
    2. 데이터베이스에 저장된 지역들의 임베딩과 코사인 유사도를 계산합니다.
    3. 가장 유사도가 높은 상위 k개의 지역을 조회하여 반환합니다.

    Args:
        request (SearchRequest): 사용자의 쿼리 및 top_k 설정이 담긴 요청 모델.
        db (Session): FastAPI의 의존성 주입을 통해 제공되는 데이터베이스 세션.

    Raises:
        HTTPException: 쿼리 텍스트를 임베딩으로 변환하는 데 실패할 경우,
            상태 코드 500으로 오류를 발생시킵니다.

    Returns:
        SearchResponse: 원본 쿼리와 함께 추천된 지역 목록을 포함하는 응답 모델.
    """
    logger.info(f"🔍 [New Request] 질문: {request.query}")
    query_vector = embedder.get_embedding(request.query)
    if not query_vector:
        raise HTTPException(status_code=500, detail="임베딩 생성 실패")

    results = search_regions_by_vector(db, query_vector, request.top_k)
    logger.info(f"🔍 검색 완료: {len(results)}건의 지역 반환")

    recommendations = [
        RegionRecommendation(
            region_id=region.region_id,
            region_name=region.region_name,
        )
        for region in results
    ]

    return SearchResponse(query=request.query, results=recommendations)
