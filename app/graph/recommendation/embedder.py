"""추천 그래프용 임베딩 인스턴스 관리."""

from functools import lru_cache

from app.integrations.embedding import EmbeddingService


@lru_cache
def get_embedder() -> EmbeddingService:
    """EmbeddingService 인스턴스를 반환합니다."""
    return EmbeddingService()
