"""사각형 기반 위치 필터링을 위한 지리 유틸리티."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

_MIN_LAT = -90.0
_MAX_LAT = 90.0
_MIN_LNG = -180.0
_MAX_LNG = 180.0
_KM_PER_LAT_DEGREE = 110.574
_KM_PER_LNG_DEGREE_EQUATOR = 111.320
_EPSILON = 1e-6


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True, slots=True)
class GeoRectangle:
    """지리 필터링에 사용하는 위경도 사각형."""

    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float

    def __post_init__(self) -> None:
        min_lat, max_lat = sorted((float(self.min_lat), float(self.max_lat)))
        min_lng, max_lng = sorted((float(self.min_lng), float(self.max_lng)))

        min_lat = _clamp(min_lat, _MIN_LAT, _MAX_LAT)
        max_lat = _clamp(max_lat, _MIN_LAT, _MAX_LAT)
        min_lng = _clamp(min_lng, _MIN_LNG, _MAX_LNG)
        max_lng = _clamp(max_lng, _MIN_LNG, _MAX_LNG)

        if math.isclose(min_lat, max_lat):
            min_lat = _clamp(min_lat - _EPSILON, _MIN_LAT, _MAX_LAT)
            max_lat = _clamp(max_lat + _EPSILON, _MIN_LAT, _MAX_LAT)
        if math.isclose(min_lng, max_lng):
            min_lng = _clamp(min_lng - _EPSILON, _MIN_LNG, _MAX_LNG)
            max_lng = _clamp(max_lng + _EPSILON, _MIN_LNG, _MAX_LNG)

        object.__setattr__(self, "min_lat", min_lat)
        object.__setattr__(self, "min_lng", min_lng)
        object.__setattr__(self, "max_lat", max_lat)
        object.__setattr__(self, "max_lng", max_lng)

    def contains(self, latitude: float, longitude: float) -> bool:
        """점이 사각형 내부(경계 포함)에 있는지 반환합니다."""
        lat = float(latitude)
        lng = float(longitude)
        return self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng

    def to_google_location_restriction_payload(self) -> dict[str, dict[str, float]]:
        """Google Places `locationRestriction` payload 형식으로 직렬화합니다."""
        return {
            "rectangle": {
                "low": {"latitude": self.min_lat, "longitude": self.min_lng},
                "high": {"latitude": self.max_lat, "longitude": self.max_lng},
            }
        }

    @classmethod
    def from_points_with_margin_km(
        cls,
        points: Iterable[tuple[float, float]],
        margin_km: float,
    ) -> GeoRectangle | None:
        """점 집합으로 사각형을 만들고 km 단위 margin만큼 확장합니다."""
        items = [(float(lat), float(lng)) for lat, lng in points]
        if not items:
            return None

        min_lat = min(lat for lat, _ in items)
        max_lat = max(lat for lat, _ in items)
        min_lng = min(lng for _, lng in items)
        max_lng = max(lng for _, lng in items)

        margin = max(0.0, float(margin_km))
        lat_margin_deg = margin / _KM_PER_LAT_DEGREE
        center_lat = _clamp((min_lat + max_lat) / 2, -89.999999, 89.999999)
        cos_lat = max(abs(math.cos(math.radians(center_lat))), _EPSILON)
        lng_margin_deg = margin / (_KM_PER_LNG_DEGREE_EQUATOR * cos_lat)

        return cls(
            min_lat=min_lat - lat_margin_deg,
            min_lng=min_lng - lng_margin_deg,
            max_lat=max_lat + lat_margin_deg,
            max_lng=max_lng + lng_margin_deg,
        )
