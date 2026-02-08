"""지역 재정렬 노드."""

import json

from app.core.logger import get_logger
from app.graph.recommendation.llm import get_llm
from app.graph.recommendation.state import GraphState, RankedRegion

logger = get_logger(__name__)


def rerank_regions(state: GraphState) -> GraphState:
    """LLM을 사용해 제약 조건을 검증하고 우선순위를 재정렬합니다."""
    candidates = state.get("candidates", [])
    preference = state.get("user_preference", {})

    if not candidates:
        return {**state, "ranked_regions": []}

    travel_range = preference.get("travel_range", "")
    budget_level = preference.get("budget_level", "")

    candidate_names = [c["region_name"] for c in candidates]

    prompt = f"""다음 여행지 후보를 사용자의 조건에 맞게 재정렬해주세요.

여행지 후보: {", ".join(candidate_names)}

사용자 조건:
- 여행 거리: {travel_range}
- 예산 수준: {budget_level}

예산 수준별 가이드라인:
- LOW: 동남아, 베트남, 동유럽, 저가 여행지 우선.
  일본, 유럽 고가 여행지는 constraints_met=false.
- MEDIUM: 중간 가격대 여행지 허용.
  북유럽, 비싼 도시 등은 constraints_met=false.
- HIGH: 대부분 여행지 추천 가능.
- VERY_HIGH: 모든 여행지 추천 가능.

재정렬 기준:
- constraints_met: 예산 가이드라인을 충족하면 true, 아니면 false
- score: 조건 만족도가 높을수록 높은 점수 (0.0~1.0)
  - 완전히 조건에 부합: 0.8~1.0
  - 부분 충족: 0.5~0.7
  - 미충족: 0.3 이하

각 여행지에 대해 JSON 배열로 답해주세요:
[{{"region_name": "도시명", "constraints_met": true/false, "score": 0.0-1.0, "reason": "재정렬 이유"}}]

JSON 배열만 출력하세요."""

    try:
        response = get_llm().invoke(prompt)
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

    except Exception as exc:
        logger.error("Reranking failed: %s", exc)
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
