"""지역 검색 서비스."""

from sqlalchemy.orm import Session

from app.models.region_embedding import RegionEmbedding


def search_regions_by_vector(db: Session, query_vector: list[float], top_k: int) -> list[RegionEmbedding]:
    """벡터 유사도 기반으로 지역을 검색합니다."""
    return (
        db.query(RegionEmbedding)
        .filter(RegionEmbedding.embedding.isnot(None))
        .order_by(RegionEmbedding.embedding.cosine_distance(query_vector))
        .limit(top_k)
        .all()
    )
