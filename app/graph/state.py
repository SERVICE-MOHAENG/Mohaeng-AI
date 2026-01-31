"""LangGraph 워크플로우 상태 정의."""

from typing import TypedDict
from uuid import UUID


class UserPreference(TypedDict, total=False):
    """사용자 선호도 입력."""

    travel_range: str  # DOMESTIC, NEAR_ASIA, SOUTHEAST_ASIA, EUROPE, LONG_HAUL
    budget_level: str  # LOW, MEDIUM, HIGH, VERY_HIGH
    main_interests: list[str]  # HISTORY, NATURE, FOOD, SHOPPING, etc.
    environment: str  # URBAN, NATURE, COASTAL, MOUNTAIN
    weather: str  # WARM, COOL, TROPICAL, etc.


class RegionCandidate(TypedDict):
    """검색된 지역 후보."""

    region_id: UUID | None
    region_name: str
    score: float


class RankedRegion(TypedDict):
    """Reranking된 지역 결과."""

    region_id: UUID | None
    region_name: str
    score: float
    reason: str
    constraints_met: bool


class GraphState(TypedDict, total=False):
    """LangGraph 워크플로우 상태."""

    # 입력
    user_preference: UserPreference
    top_k: int

    # 변환된 쿼리
    transformed_query: str

    # 1차 검색 결과
    candidates: list[RegionCandidate]

    # Reranking 결과
    ranked_regions: list[RankedRegion]

    # 최종 응답
    final_recommendations: list[RankedRegion]

    # 에러 처리
    error: str | None
