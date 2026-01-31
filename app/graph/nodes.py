"""LangGraph 워크플로우 노드 함수."""

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.graph.state import GraphState, RegionCandidate
from app.models.region_embedding import RegionEmbedding
from app.services.embedding import EmbeddingService

logger = get_logger(__name__)

embedder = EmbeddingService()


def transform_input(state: GraphState) -> GraphState:
    """사용자 선호도를 검색용 자연어 쿼리로 변환합니다."""
    preference = state.get("user_preference", {})

    query_parts = []

    if interests := preference.get("main_interests"):
        interest_map = {
            "HISTORY": "역사와 문화 유적",
            "NATURE": "자연 경관",
            "FOOD": "맛집과 음식 문화",
            "SHOPPING": "쇼핑",
            "ACTIVITY": "액티비티와 모험",
            "RELAXATION": "휴양과 힐링",
        }
        mapped = [interest_map.get(i, i) for i in interests]
        query_parts.append(f"관심사: {', '.join(mapped)}")

    if environment := preference.get("environment"):
        env_map = {
            "URBAN": "도시적인 분위기",
            "NATURE": "자연 친화적인 환경",
            "COASTAL": "해안가와 바다",
            "MOUNTAIN": "산악 지역",
        }
        query_parts.append(env_map.get(environment, environment))

    if weather := preference.get("weather"):
        weather_map = {
            "WARM": "따뜻한 날씨",
            "COOL": "시원한 날씨",
            "TROPICAL": "열대 기후",
        }
        query_parts.append(weather_map.get(weather, weather))

    if travel_range := preference.get("travel_range"):
        range_map = {
            "DOMESTIC": "국내 여행",
            "NEAR_ASIA": "가까운 아시아 국가",
            "SOUTHEAST_ASIA": "동남아시아",
            "EUROPE": "유럽",
            "LONG_HAUL": "장거리 여행",
        }
        query_parts.append(range_map.get(travel_range, travel_range))

    transformed_query = "여행지 추천: " + ", ".join(query_parts) if query_parts else "인기 있는 여행지 추천"

    logger.info("Query transformed: %s", transformed_query)

    return {**state, "transformed_query": transformed_query}


def search_regions(state: GraphState, db: Session) -> GraphState:
    """벡터 유사도 기반으로 지역을 검색합니다."""
    query = state.get("transformed_query", "")
    top_k = state.get("top_k", 10)

    query_vector = embedder.get_embedding(query)
    if not query_vector:
        logger.error("Failed to generate embedding for query")
        return {**state, "error": "임베딩 생성 실패", "candidates": []}

    results = (
        db.query(RegionEmbedding)
        .filter(RegionEmbedding.embedding.isnot(None))
        .order_by(RegionEmbedding.embedding.cosine_distance(query_vector))
        .limit(top_k)
        .all()
    )

    candidates: list[RegionCandidate] = [
        {
            "region_id": r.region_id,
            "region_name": r.region_name,
            "score": 1.0 - (i * 0.05),
        }
        for i, r in enumerate(results)
    ]

    logger.info("Found %d region candidates", len(candidates))

    return {**state, "candidates": candidates}
