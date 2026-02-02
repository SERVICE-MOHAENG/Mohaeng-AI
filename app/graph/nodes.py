"""LangGraph 워크플로우 노드 함수."""

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.graph.state import GraphState, RankedRegion, RegionCandidate
from app.models.region_embedding import RegionEmbedding
from app.services.embedding import EmbeddingService

logger = get_logger(__name__)

embedder = EmbeddingService()
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)


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


def search_regions(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """벡터 유사도 기반으로 지역을 검색합니다."""
    db = config["configurable"]["db"]
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
            "score": max(0.0, 1.0 - (i * 0.05)),
        }
        for i, r in enumerate(results)
    ]

    logger.info("Found %d region candidates", len(candidates))

    return {**state, "candidates": candidates}


def rerank_regions(state: GraphState) -> GraphState:
    """LLM을 사용하여 제약 조건을 검증하고 순위를 재조정합니다."""
    candidates = state.get("candidates", [])
    preference = state.get("user_preference", {})

    if not candidates:
        return {**state, "ranked_regions": []}

    travel_range = preference.get("travel_range", "")
    budget_level = preference.get("budget_level", "")

    candidate_names = [c["region_name"] for c in candidates]

    prompt = f"""다음 여행지 후보들을 사용자 조건에 맞게 평가해주세요.

여행지 후보: {", ".join(candidate_names)}

사용자 조건:
- 여행 거리: {travel_range}
- 예산 수준: {budget_level}

예산 수준별 가이드라인:
- LOW: 동남아(태국, 베트남), 동유럽(체코, 헝가리) 등 물가 저렴한 지역 우선.
  서유럽, 북미, 일본 등 물가 높은 지역은 constraints_met=false.
- MEDIUM: 남유럽, 대만, 말레이시아 등 중간 물가 지역 적합.
  스위스, 북유럽 등 매우 비싼 지역은 constraints_met=false.
- HIGH: 대부분 지역 추천 가능. 물가 제약 적음.
- VERY_HIGH: 모든 지역 추천 가능.

평가 기준:
- constraints_met: 예산 가이드라인에 부합하면 true, 아니면 false
- score: 예산 적합도가 높을수록 높은 점수 (0.0~1.0)
  - 예산에 딱 맞는 지역: 0.8~1.0
  - 예산에 적당한 지역: 0.5~0.7
  - 예산에 맞지 않는 지역: 0.3 이하

각 여행지에 대해 JSON 배열로 응답해주세요:
[{{"region_name": "도시명", "constraints_met": true/false, "score": 0.0-1.0, "reason": "평가 이유"}}]

JSON 배열만 응답하세요."""

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        evaluations = json.loads(content)

        region_map = {c["region_name"]: c for c in candidates}
        ranked_regions: list[RankedRegion] = []

        for evaluation in evaluations:
            name = evaluation.get("region_name", "")
            if name in region_map:
                original = region_map[name]
                ranked_regions.append(
                    {
                        "region_id": original["region_id"],
                        "region_name": name,
                        "score": evaluation.get("score", 0.5),
                        "reason": evaluation.get("reason", ""),
                        "constraints_met": evaluation.get("constraints_met", True),
                    }
                )

        ranked_regions.sort(key=lambda x: (-x["constraints_met"], -x["score"]))

        logger.info("Reranked %d regions", len(ranked_regions))

        return {**state, "ranked_regions": ranked_regions}

    except Exception as e:
        logger.error("Reranking failed: %s", e)
        fallback: list[RankedRegion] = [
            {
                "region_id": c["region_id"],
                "region_name": c["region_name"],
                "score": c["score"],
                "reason": "AI 추천",
                "constraints_met": True,
            }
            for c in candidates
        ]
        return {**state, "ranked_regions": fallback}


def generate_recommendations(state: GraphState) -> GraphState:
    """최종 추천 결과와 개인화된 추천 사유를 생성합니다."""
    ranked_regions = state.get("ranked_regions", [])
    preference = state.get("user_preference", {})
    top_k = state.get("top_k", 3)

    filtered = [r for r in ranked_regions if r["constraints_met"]][:top_k]

    if not filtered and ranked_regions:
        filtered = ranked_regions[:top_k]
        logger.info("Fallback: no regions met all constraints")

    if not filtered:
        return {**state, "final_recommendations": [], "error": "추천 가능한 여행지가 없습니다"}

    interests = preference.get("main_interests", [])
    interest_text = ", ".join(interests) if interests else "다양한 경험"

    prompt = f"""다음 여행지들에 대해 개인화된 추천 사유를 작성해주세요.

여행지: {", ".join([r["region_name"] for r in filtered])}
사용자 관심사: {interest_text}

각 여행지별로 1-2문장의 추천 사유를 JSON 배열로 작성해주세요:
[{{"region_name": "도시명", "reason": "추천 사유"}}]

JSON 배열만 응답하세요."""

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        reasons = json.loads(content)
        reason_map = {r["region_name"]: r["reason"] for r in reasons}

        final: list[RankedRegion] = []
        for region in filtered:
            final.append(
                {
                    **region,
                    "reason": reason_map.get(region["region_name"], region["reason"]),
                }
            )

        logger.info("Generated %d final recommendations", len(final))

        return {**state, "final_recommendations": final}

    except Exception as e:
        logger.error("Recommendation generation failed: %s", e)
        return {**state, "final_recommendations": filtered}
