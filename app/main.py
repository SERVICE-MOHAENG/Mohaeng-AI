from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.city import City
from app.services.embedding import EmbeddingService

app = FastAPI()

# [권장] EmbeddingService를 모듈 로드 시점에 초기화하면,
# OPENAI_API_KEY가 설정되지 않았을 때 서버 시작과 동시에 실패하게 됩니다.
# 테스트 용이성 및 유연성을 위해 FastAPI의 의존성 주입 패턴 (Depends) 사용을 권장합니다.
# 예: def get_embedder(): return EmbeddingService()
#      @app.post("/search", embedder: EmbeddingService = Depends(get_embedder))
embedder = EmbeddingService()


class SearchRequest(BaseModel):
    """검색 요청을 위한 Pydantic 모델."""

    query: str
    top_k: int = Field(default=3, ge=1, le=20)


@app.get("/")
def health_check():
    """서버의 상태를 확인하는 Health Check 엔드포인트."""
    return {"status": "ok", "message": "Mohaeng AI Server is running 🚀"}


@app.post("/search")
def search_cities(request: SearchRequest, db: Session = Depends(get_db)):  # noqa: B008
    """
    사용자의 쿼리를 받아 의미적으로 유사한 도시를 검색하여 추천.

    Args:
        request (SearchRequest): 사용자 쿼리와 top_k 값이 포함된 요청 모델.
        db (Session, optional): FastAPI 의존성 주입으로 생성된 DB 세션.

    Raises:
        HTTPException: 임베딩 생성에 실패했을 때 500 오류를 발생시킴.

    Returns:
        dict: 사용자의 쿼리와 추천 도시 목록이 포함된 응답.
    """
    print(f"🔍 [New Request] 질문: {request.query}")
    query_vector = embedder.get_embedding(request.query)
    if not query_vector:
        raise HTTPException(status_code=500, detail="임베딩 생성 실패")

    results = db.query(City).order_by(City.embedding.cosine_distance(query_vector)).limit(request.top_k).all()

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
