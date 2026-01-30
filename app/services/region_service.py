from sqlalchemy.orm import Session

from app.models.region_embedding import RegionEmbedding


def search_regions_by_vector(db: Session, query_vector: list[float], top_k: int) -> list[RegionEmbedding]:
    """벡터 유사도 기반으로 지역을 검색합니다.

    Args:
        db: 데이터베이스 세션.
        query_vector: 검색할 쿼리의 임베딩 벡터.
        top_k: 반환할 최대 지역 수.

    Returns:
        코사인 유사도 순으로 정렬된 지역 임베딩 목록.
    """
    return (
        db.query(RegionEmbedding)
        .filter(RegionEmbedding.embedding.isnot(None))
        .order_by(RegionEmbedding.embedding.cosine_distance(query_vector))
        .limit(top_k)
        .all()
    )
