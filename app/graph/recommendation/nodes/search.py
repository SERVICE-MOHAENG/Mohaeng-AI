"""지역 검색 노드."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.logger import get_logger
from app.graph.recommendation.embedder import get_embedder
from app.graph.recommendation.state import GraphState, RegionCandidate
from app.models.region_embedding import RegionEmbedding

logger = get_logger(__name__)


def search_regions(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """벡터 검색을 수행해 지역 후보를 반환합니다."""
    db = config["configurable"]["db"]
    query = state.get("transformed_query", "")
    top_k = state.get("top_k", 10)

    query_vector = get_embedder().get_embedding(query)
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
            "score": max(0.0, 1.0 - (i * 0.05)),
        }
        for i, r in enumerate(results)
    ]

    logger.info("Found %d region candidates", len(candidates))

    return {**state, "candidates": candidates}
