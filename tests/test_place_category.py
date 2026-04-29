"""Google Places type의 Mohaeng 장소 카테고리 매핑 테스트."""

from __future__ import annotations

import pytest

from app.core.place_category import PlaceCategory, resolve_place_category


@pytest.mark.parametrize(
    "place_type",
    [
        "japanese_restaurant",
        "steak_house",
        "seafood_restaurant",
        "korean_barbecue_restaurant",
    ],
)
def test_resolve_place_category_maps_restaurant_types_to_food(place_type: str) -> None:
    assert resolve_place_category(place_type, []).value == PlaceCategory.FOOD


def test_resolve_place_category_uses_types_when_primary_type_is_generic() -> None:
    assert resolve_place_category("point_of_interest", ["establishment", "seafood_restaurant"]).value == "FOOD"


@pytest.mark.parametrize("place_type", ["cafe", "coffee_shop", "dessert_shop", "tea_house"])
def test_resolve_place_category_maps_cafe_and_dessert_types_to_cafe(place_type: str) -> None:
    assert resolve_place_category(place_type, ["food", "point_of_interest"]).value == "CAFE"


@pytest.mark.parametrize(
    ("place_type", "expected"),
    [
        ("museum", "CULTURE"),
        ("tourist_attraction", "ATTRACTION"),
        ("beach", "NATURE"),
        ("shopping_mall", "SHOPPING"),
        ("hotel", "LODGING"),
        ("train_station", "TRANSPORT"),
        ("spa", "WELLNESS"),
        ("travel_agency", "SERVICE"),
    ],
)
def test_resolve_place_category_maps_representative_domain_types(place_type: str, expected: str) -> None:
    assert resolve_place_category(place_type, []).value == expected


@pytest.mark.parametrize("place_type", [None, "", "unknown_type", "establishment", "point_of_interest"])
def test_resolve_place_category_falls_back_to_other(place_type: str | None) -> None:
    assert resolve_place_category(place_type, []).value == "OTHER"
