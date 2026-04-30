"""로드맵 동선 최적화 정책 테스트."""

from __future__ import annotations

import pytest

from app.core.route_optimizer import haversine_distance_km, is_food_anchor, optimize_daily_route


def _place(
    name: str,
    category: str,
    latitude: float | None,
    longitude: float | None,
    *,
    section: str = "MORNING",
) -> dict:
    return {
        "place_name": name,
        "place_id": name,
        "place_category": category,
        "latitude": latitude,
        "longitude": longitude,
        "section": section,
    }


def _names(places: list[dict]) -> list[str]:
    return [place["place_name"] for place in places]


def test_haversine_distance_km_returns_zero_for_same_coordinate() -> None:
    assert haversine_distance_km(37.5, 127.0, 37.5, 127.0) == pytest.approx(0.0)


def test_is_food_anchor_uses_only_place_category() -> None:
    assert is_food_anchor(_place("breakfast", "FOOD", 37.5, 127.0, section="MORNING")) is True
    assert is_food_anchor(_place("lunch museum", "CULTURE", 37.5, 127.0, section="LUNCH")) is False


def test_optimize_daily_route_optimizes_all_places_when_no_food_anchor_exists() -> None:
    places = [
        _place("A", "CULTURE", 37.5, 127.0),
        _place("B", "NATURE", 37.5, 127.09),
        _place("C", "SHOPPING", 37.5, 127.01),
    ]

    optimized = optimize_daily_route(places)

    assert _names(optimized) == ["A", "C", "B"]


def test_optimize_daily_route_keeps_food_anchors_and_reorders_between_them() -> None:
    places = [
        _place("before", "ATTRACTION", 37.5, 127.1),
        _place("lunch", "FOOD", 37.5, 127.0, section="LUNCH"),
        _place("far", "CULTURE", 37.5, 127.09),
        _place("near", "NATURE", 37.5, 127.01),
        _place("dinner", "FOOD", 37.5, 127.02, section="DINNER"),
        _place("after", "SHOPPING", 37.5, 127.03),
    ]

    optimized = optimize_daily_route(places)

    assert _names(optimized) == ["before", "lunch", "near", "far", "dinner", "after"]
    assert optimized[1]["place_category"] == "FOOD"
    assert optimized[4]["place_category"] == "FOOD"


def test_optimize_daily_route_preserves_order_when_segment_has_missing_coordinates() -> None:
    places = [
        _place("A", "CULTURE", 37.5, 127.0),
        _place("B", "NATURE", None, None),
        _place("C", "SHOPPING", 37.5, 127.01),
    ]

    optimized = optimize_daily_route(places)

    assert _names(optimized) == ["A", "B", "C"]


def test_optimize_daily_route_preserves_segment_order_when_anchor_has_missing_coordinates() -> None:
    places = [
        _place("lunch", "FOOD", None, None, section="LUNCH"),
        _place("far", "CULTURE", 37.5, 127.09),
        _place("near", "NATURE", 37.5, 127.01),
        _place("dinner", "FOOD", 37.5, 127.02, section="DINNER"),
    ]

    optimized = optimize_daily_route(places)

    assert _names(optimized) == ["lunch", "far", "near", "dinner"]


@pytest.mark.parametrize("places", [[], [_place("A", "CULTURE", 37.5, 127.0)]])
def test_optimize_daily_route_handles_zero_and_one_place(places: list[dict]) -> None:
    assert optimize_daily_route(places) == places
