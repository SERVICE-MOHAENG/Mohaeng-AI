"""로드맵 그래프 상태 정의."""

from typing import TypedDict

from app.schemas.enums import Region


class RoadmapSlot(TypedDict):
    """방문 슬롯 단위의 검색 의도."""

    section: str
    area: str
    keyword: str


class RoadmapDayPlan(TypedDict):
    """일자별 스켈레톤 플랜."""

    day_number: int
    region: Region
    slots: list[RoadmapSlot]


class RoadmapState(TypedDict, total=False):
    """로드맵 생성 그래프 상태."""

    course_request: dict
    trip_days: int
    slot_min: int
    slot_max: int
    skeleton_plan: list[RoadmapDayPlan]
    skeleton_warnings: list[str]
    fetched_places: dict[str, list]  # 슬롯 키 -> Place 목록 매핑
    error: str | None
