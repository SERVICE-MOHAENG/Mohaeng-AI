"""로드맵 장소 동선 최적화 정책."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.core.place_category import PlaceCategory

_EARTH_RADIUS_KM = 6371.0
_IMPROVEMENT_EPSILON = 1e-9


def _coordinate(place: dict) -> tuple[float, float] | None:
    lat = place.get("latitude")
    lon = place.get("longitude")
    if lat is None or lon is None:
        return None

    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat_value <= 90 and -180 <= lon_value <= 180):
        return None
    return lat_value, lon_value


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 Haversine 직선거리(km)를 계산합니다."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_between(left: dict, right: dict) -> float | None:
    left_coordinate = _coordinate(left)
    right_coordinate = _coordinate(right)
    if left_coordinate is None or right_coordinate is None:
        return None
    return haversine_distance_km(left_coordinate[0], left_coordinate[1], right_coordinate[0], right_coordinate[1])


def is_food_anchor(place: dict) -> bool:
    """FOOD 장소인지 확인합니다. section 값은 anchor 판별에 사용하지 않습니다."""
    return str(place.get("place_category") or "").strip().upper() == PlaceCategory.FOOD.value


def _path_cost(segment: Sequence[dict], start_anchor: dict | None, end_anchor: dict | None) -> float:
    if not segment:
        return 0.0

    cost = 0.0
    if start_anchor is not None:
        distance = _distance_between(start_anchor, segment[0])
        if distance is not None:
            cost += distance

    for index in range(1, len(segment)):
        distance = _distance_between(segment[index - 1], segment[index])
        if distance is not None:
            cost += distance

    if end_anchor is not None:
        distance = _distance_between(segment[-1], end_anchor)
        if distance is not None:
            cost += distance

    return cost


def _nearest_neighbor_order(segment: list[dict], start_anchor: dict | None) -> list[dict]:
    remaining = list(segment)
    ordered: list[dict] = []

    if start_anchor is not None and _coordinate(start_anchor) is not None:
        current = start_anchor
    else:
        current = remaining.pop(0)
        ordered.append(current)

    while remaining:
        current_coordinate = _coordinate(current)
        if current_coordinate is None:
            ordered.extend(remaining)
            break

        next_index = min(
            range(len(remaining)),
            key=lambda index: (
                _distance_between(current, remaining[index]) or math.inf,
                segment.index(remaining[index]),
            ),
        )
        current = remaining.pop(next_index)
        ordered.append(current)

    return ordered


def _two_opt(segment: list[dict], start_anchor: dict | None, end_anchor: dict | None) -> list[dict]:
    best = list(segment)
    if len(best) < 2:
        return best

    improved = True
    while improved:
        improved = False
        best_cost = _path_cost(best, start_anchor, end_anchor)
        for start_index in range(len(best) - 1):
            for end_index in range(start_index + 1, len(best)):
                candidate = (
                    best[:start_index] + list(reversed(best[start_index : end_index + 1])) + best[end_index + 1 :]
                )
                candidate_cost = _path_cost(candidate, start_anchor, end_anchor)
                if candidate_cost + _IMPROVEMENT_EPSILON < best_cost:
                    best = candidate
                    improved = True
                    break
            if improved:
                break

    return best


def _optimize_segment(segment: list[dict], start_anchor: dict | None, end_anchor: dict | None) -> list[dict]:
    if len(segment) < 2:
        return list(segment)
    if any(_coordinate(place) is None for place in segment):
        return list(segment)

    ordered = _nearest_neighbor_order(segment, start_anchor)
    return _two_opt(ordered, start_anchor, end_anchor)


def optimize_daily_route(places: list[dict]) -> list[dict]:
    """FOOD anchor를 고정하고 anchor 사이의 비음식 장소만 거리 기반으로 재정렬합니다."""
    if len(places) < 3:
        return list(places)

    optimized: list[dict] = []
    segment: list[dict] = []
    previous_anchor: dict | None = None

    for place in places:
        if is_food_anchor(place):
            optimized.extend(_optimize_segment(segment, previous_anchor, place))
            optimized.append(place)
            previous_anchor = place
            segment = []
        else:
            segment.append(place)

    optimized.extend(_optimize_segment(segment, previous_anchor, None))
    return optimized
