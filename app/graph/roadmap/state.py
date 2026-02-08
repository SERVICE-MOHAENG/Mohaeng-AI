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
    """로드맵 생성 그래프 상태.

    Keys:
        course_request: 요청 페이로드
        trip_days: 여행 일수
        slot_min: 슬롯 최소 개수
        slot_max: 슬롯 최대 개수
        skeleton_plan: 스켈레톤 플랜
        skeleton_warnings: 스켈레톤 경고 목록
        fetched_places: 슬롯 키별 장소 목록
        final_roadmap: 최종 로드맵 응답
        error: 오류 메시지
    """

    course_request: dict
    trip_days: int
    slot_min: int
    slot_max: int
    skeleton_plan: list[RoadmapDayPlan]
    skeleton_warnings: list[str]
    fetched_places: dict[str, list]
    final_roadmap: dict | None
    error: str | None
