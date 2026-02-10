"""로드맵 수정 그래프 유틸리티."""

import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 직선 거리(km)를 반환합니다."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def reorder_visit_sequence(places: list[dict]) -> list[dict]:
    """places 리스트의 visit_sequence를 1부터 순차 재정렬합니다."""
    for index, place in enumerate(places, start=1):
        place["visit_sequence"] = index
    return places


def build_diff_key(day_number: int, visit_sequence: int) -> str:
    """수정된 노드 식별 키를 생성합니다."""
    return f"day{day_number}_place{visit_sequence}"
