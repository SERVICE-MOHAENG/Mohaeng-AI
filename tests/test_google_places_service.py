"""Google Places 응답 매핑 테스트."""

from __future__ import annotations

from app.services.google_places_service import GooglePlacesService


def test_map_place_maps_primary_type() -> None:
    service = GooglePlacesService.__new__(GooglePlacesService)

    place = service._map_place(
        {
            "id": "places/test-place",
            "displayName": {"text": "테스트 식당"},
            "formattedAddress": "서울 중구",
            "location": {"latitude": 37.5665, "longitude": 126.978},
            "googleMapsUri": "https://maps.google.com/test",
            "primaryType": "restaurant",
            "types": ["restaurant", "food", "point_of_interest"],
        }
    )

    assert place is not None
    assert place.primary_type == "restaurant"
    assert place.types == ["restaurant", "food", "point_of_interest"]


def test_map_place_allows_missing_primary_type() -> None:
    service = GooglePlacesService.__new__(GooglePlacesService)

    place = service._map_place(
        {
            "id": "places/test-place",
            "displayName": {"text": "테스트 명소"},
            "formattedAddress": "서울 종로구",
            "location": {"latitude": 37.5796, "longitude": 126.977},
            "types": ["tourist_attraction"],
        }
    )

    assert place is not None
    assert place.primary_type is None
