from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.city import City
from app.services.embedding import EmbeddingService

app = FastAPI()

embedder = EmbeddingService()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Mohaeng AI Server is running 🚀"}


@app.post("/search")
def search_cities(request: SearchRequest, db: Session = Depends(get_db)):  # noqa: B008 # noqa: B008    print(f"🔍 [New Request] 질문: {request.query}")
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
                "description": city.description[:150] + "...",
                "reason": "AI 추천 결과",
            }
        )

    return {"query": request.query, "results": recommendations}
