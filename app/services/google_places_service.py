"""Google Places API 서비스 구현."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import requests

from app.core.config import get_settings
from app.core.logger import get_logger
from app.schemas.place import Place, PlaceGeometry
from app.services.places_service import PlacesServiceProtocol

logger = get_logger(__name__)


class GooglePlacesError(RuntimeError):
    """Google Places API 호출 오류입니다."""


class GooglePlacesService(PlacesServiceProtocol):
    """Google Places API를 사용하는 Places 서비스입니다."""

    _BASE_URL = "https://places.googleapis.com/v1"
    _SEARCH_PATH = "/places:searchText"

    _SEARCH_FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.rating,places.userRatingCount,places.types,places.googleMapsUri"
    )
    _DETAILS_FIELD_MASK = "id,displayName,formattedAddress,location,rating,userRatingCount,types,googleMapsUri"

    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 10,
        page_size: int = 5,
        language_code: str = "ko",
    ) -> None:
        if not api_key:
            raise GooglePlacesError("GOOGLE_PLACES_API_KEY가 설정되어 있지 않습니다.")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._page_size = page_size
        self._language_code = language_code.strip() if language_code else ""

    def close(self) -> None:
        """Close resources (kept for API symmetry/context manager use)."""
        # Requests sessions are created per-call for thread safety, so nothing to close here.
        return None

    def __enter__(self) -> "GooglePlacesService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @classmethod
    def from_settings(cls) -> "GooglePlacesService":
        """환경 설정으로부터 서비스 인스턴스를 생성합니다."""
        settings = get_settings()
        timeout_seconds = settings.GOOGLE_PLACES_TIMEOUT_SECONDS
        if not settings.GOOGLE_PLACES_API_KEY:
            logger.error("GOOGLE_PLACES_API_KEY가 설정되어 있지 않습니다.")
        return cls(
            api_key=settings.GOOGLE_PLACES_API_KEY or "",
            timeout_seconds=timeout_seconds,
            language_code=settings.GOOGLE_PLACES_LANGUAGE_CODE,
        )

    async def search(self, query: str) -> list[Place]:
        """검색 쿼리로 장소를 검색합니다."""
        if not query.strip():
            return []

        payload = {"textQuery": query, "pageSize": self._page_size}
        if self._language_code:
            payload["languageCode"] = self._language_code
        data = await self._request(
            method="POST",
            url=f"{self._BASE_URL}{self._SEARCH_PATH}",
            payload=payload,
            params=None,
            field_mask=self._SEARCH_FIELD_MASK,
        )

        places_raw = (data or {}).get("places", [])
        places = [place for place in (self._map_place(item) for item in places_raw) if place]
        return self._filter_and_rank(places)

    async def details(self, place_id: str) -> Place | None:
        """장소 상세 정보를 조회합니다."""
        if not place_id:
            return None

        resource = place_id if place_id.startswith("places/") else f"places/{place_id}"
        params = {}
        if self._language_code:
            params["languageCode"] = self._language_code

        data = await self._request(
            method="GET",
            url=f"{self._BASE_URL}/{resource}",
            payload=None,
            params=params or None,
            field_mask=self._DETAILS_FIELD_MASK,
        )

        return self._map_place(data or {})

    async def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        params: dict[str, Any] | None,
        field_mask: str,
    ) -> dict[str, Any] | None:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }

        def _send() -> requests.Response:
            # Create a session per request to avoid cross-thread session reuse.
            with requests.Session() as session:
                return session.request(
                    method=method,
                    url=url,
                    json=payload,
                    params=params,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )

        try:
            response = await asyncio.to_thread(_send)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response else None
            body = (response.text or "")[:200] if response else ""
            logger.error("Google Places API 오류: status=%s body=%s", status_code, body)
            return None
        except requests.RequestException as exc:
            logger.error("Google Places API 요청 실패: %s", exc)
            return None
        except ValueError as exc:
            logger.error("Google Places API 응답 파싱 실패: %s", exc)
            return None

    def _map_place(self, raw: dict[str, Any]) -> Place | None:
        display_name = raw.get("displayName") or {}
        name = display_name.get("text")
        location = raw.get("location") or {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        place_id = raw.get("id") or raw.get("placeId")

        if not (name and place_id and latitude is not None and longitude is not None):
            return None

        return Place(
            place_id=place_id,
            name=name,
            address=raw.get("formattedAddress"),
            geometry=PlaceGeometry(latitude=latitude, longitude=longitude),
            url=raw.get("googleMapsUri"),
            rating=float(raw.get("rating") or 0.0),
            user_ratings_total=int(raw.get("userRatingCount") or 0),
            types=raw.get("types") or [],
        )

    def _filter_and_rank(self, places: list[Place]) -> list[Place]:
        filtered = [
            place
            for place in places
            if place.rating >= self.MIN_RATING and place.user_ratings_total >= self.MIN_REVIEWS
        ]
        return sorted(filtered, key=lambda p: (p.rating, p.user_ratings_total), reverse=True)


@lru_cache(maxsize=1)
def get_google_places_service() -> GooglePlacesService:
    """Process-wide singleton for configuration reuse."""
    return GooglePlacesService.from_settings()
