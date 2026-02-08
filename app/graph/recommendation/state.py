"""`LangGraph` 워크플로우 상태 정의."""

from typing import TypedDict
from uuid import UUID


class UserPreference(TypedDict, total=False):
    """사용자 선호도 입력.

    Fields:
        `travel_range`: `DOMESTIC`, `NEAR_ASIA`, `SOUTHEAST_ASIA`, `EUROPE`, `LONG_HAUL`
        `budget_level`: `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`
        `main_interests`: `HISTORY`, `NATURE`, `FOOD`, `SHOPPING` 등
        `environment`: `URBAN`, `NATURE`, `COASTAL`, `MOUNTAIN`
        `weather`: `WARM`, `COOL`, `TROPICAL` 등
    """

    travel_range: str
    budget_level: str
    main_interests: list[str]
    environment: str
    weather: str


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
    """`LangGraph` 워크플로우 상태.

    Keys:
        `user_preference`: 사용자 선호도 입력
        `top_k`: 검색/추천 상위 K
        `transformed_query`: 전처리된 쿼리 문자열
        `candidates`: 1차 검색 결과
        `ranked_regions`: 재정렬 결과
        `final_recommendations`: 최종 추천 결과
        `error`: 처리 중 발생한 에러 메시지
    """

    user_preference: UserPreference
    top_k: int
    transformed_query: str
    candidates: list[RegionCandidate]
    ranked_regions: list[RankedRegion]
    final_recommendations: list[RankedRegion]
    error: str | None
