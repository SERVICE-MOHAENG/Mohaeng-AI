import logging

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.city import City
from app.services.embedding import EmbeddingService

app = FastAPI()
logger = logging.getLogger(__name__)

# [권장] EmbeddingService를 모듈 로드 시점에 초기화하면,
# OPENAI_API_KEY가 설정되지 않았을 때 서버 시작과 동시에 실패하게 됩니다.
# 테스트 용이성 및 유연성을 위해 FastAPI의 의존성 주입 패턴 (Depends) 사용을 권장합니다.
# 예: def get_embedder(): return EmbeddingService()
#      @app.post("/search", embedder: EmbeddingService = Depends(get_embedder))
embedder = EmbeddingService()


class SearchRequest(BaseModel):
    """검색 API에 대한 요청 본문(body) 모델.

    Attributes:
        query (str): 사용자가 검색할 자연어 텍스트. 최소 1자 이상이어야 합니다.
        top_k (int): 반환받을 추천 도시의 최대 개수. 1에서 20 사이의 값.
    """

    query: str = Field(..., min_length=1, description="검색할 자연어 텍스트 (최소 1자 이상)")
    top_k: int = Field(default=3, ge=1, le=20, description="추천받을 도시의 수")


@app.get("/")
def health_check() -> dict:
    """서버의 현재 동작 상태를 확인합니다.

    Returns:
        dict: 서버가 정상적으로 실행 중임을 나타내는 상태 메시지.
    """
    return {"status": "ok", "message": "Mohaeng AI Server is running 🚀"}


@app.post("/search")
def search_cities(request: SearchRequest, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    """사용자 쿼리를 기반으로 의미상 가장 유사한 도시 목록을 반환합니다.

    이 엔드포인트는 다음 단계를 거칩니다:
    1. 요청 본문에서 받은 쿼리 텍스트를 임베딩 벡터로 변환합니다.
    2. 데이터베이스에 저장된 도시들의 임베딩과 코사인 유사도를 계산합니다.
    3. 가장 유사도가 높은 상위 k개의 도시를 조회하여 반환합니다.

    Args:
        request (SearchRequest): 사용자의 쿼리 및 top_k 설정이 담긴 요청 모델.
        db (Session): FastAPI의 의존성 주입을 통해 제공되는 데이터베이스 세션.

    Raises:
        HTTPException: 쿼리 텍스트를 임베딩으로 변환하는 데 실패할 경우,
            상태 코드 500으로 오류를 발생시킵니다.

    Returns:
        dict: 원본 쿼리와 함께 추천된 도시 목록('results')을 포함하는 딕셔너리.
    """
    logger.info(f"🔍 [New Request] 질문: {request.query}")
    query_vector = embedder.get_embedding(request.query)
    if not query_vector:
        raise HTTPException(status_code=500, detail="임베딩 생성 실패")

    results = (
        db.query(City)
        .filter(City.embedding.isnot(None))  # NULL 임베딩 제외
        .order_by(City.embedding.cosine_distance(query_vector))
        .limit(request.top_k)
        .all()
    )
    logger.info(f"🔍 검색 완료: {len(results)}건의 도시 반환")

    recommendations = []
    for city in results:
        recommendations.append(
            {
                "city": city.name,
                "country": city.country,
                "description": (city.description or "")[:150] + "...",
                "reason": "AI 추천 결과",
            }
        )

    return {"query": request.query, "results": recommendations}
