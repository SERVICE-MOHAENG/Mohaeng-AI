"""추천 생성 노드."""

import json

from app.core.logger import get_logger
from app.graph.recommendation.llm import get_llm
from app.graph.recommendation.state import GraphState, RankedRegion

logger = get_logger(__name__)


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

    prompt = f"""다음 여행지에 대한 개인화된 추천 사유를 작성해주세요.

여행지: {", ".join([r["region_name"] for r in filtered])}
사용자 관심사: {interest_text}

각 여행지별로 1-2문장의 추천 사유를 JSON 배열로 작성해주세요:
[{{"region_name": "도시명", "reason": "추천 사유"}}]

JSON 배열만 출력하세요."""

    try:
        response = get_llm().invoke(prompt)
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

    except Exception as exc:
        logger.error("Recommendation generation failed: %s", exc)
        return {**state, "final_recommendations": filtered}
