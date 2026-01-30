from sqlalchemy.orm import Session

from app.models.city import City


def search_cities_by_vector(db: Session, query_vector: list[float], top_k: int) -> list[City]:
    """벡터 유사도 기반으로 도시를 검색합니다.

    Args:
        db: 데이터베이스 세션.
        query_vector: 검색할 쿼리의 임베딩 벡터.
        top_k: 반환할 최대 도시 수.

    Returns:
        코사인 유사도 순으로 정렬된 도시 목록.
    """
    return (
        db.query(City)
        .filter(City.embedding.isnot(None))
        .order_by(City.embedding.cosine_distance(query_vector))
        .limit(top_k)
        .all()
    )
