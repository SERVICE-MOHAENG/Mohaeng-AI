"""Google Places API 서비스 구현."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import requests

from app.core.config import get_settings
from app.core.geo import GeoRectangle
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy, to_requests_timeout
from app.schemas.place import Place, PlaceGeometry
from app.services.places_service import PlacesServiceProtocol

logger = get_logger(__name__)


class GooglePlacesError(RuntimeError):
    """Google Places 호출 설정 실패 시 발생하는 예외."""


class GooglePlacesService(PlacesServiceProtocol):
    """Google Places API 기반 Places 서비스."""

    _BASE_URL = "https://places.googleapis.com/v1"
    _SEARCH_PATH = "/places:searchText"

    _SEARCH_FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.googleMapsUri"
    )
    _DETAILS_FIELD_MASK = "id,displayName,formattedAddress,location,types,googleMapsUri"

    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 10,
        page_size: int = 5,
        language_code: str = "ko",
    ) -> None:
        if not api_key:
            raise GooglePlacesError("GOOGLE_PLACES_API_KEY is not configured.")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._page_size = page_size
        self._language_code = language_code.strip() if language_code else ""

    def close(self) -> None:
        """리소스를 정리합니다(컨텍스트 매니저 대칭성 유지)."""
        return None

    def __enter__(self) -> GooglePlacesService:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @classmethod
    def from_settings(cls) -> GooglePlacesService:
        """애플리케이션 설정으로 서비스 인스턴스를 생성합니다."""
        settings = get_settings()
        timeout_policy = get_timeout_policy(settings)
        timeout_seconds = timeout_policy.google_places_timeout_seconds
        if not settings.GOOGLE_PLACES_API_KEY:
            logger.error("GOOGLE_PLACES_API_KEY is not configured.")
        return cls(
            api_key=settings.GOOGLE_PLACES_API_KEY or "",
            timeout_seconds=timeout_seconds,
            language_code=settings.GOOGLE_PLACES_LANGUAGE_CODE,
        )

    async def search(
        self,
        query: str,
        price_levels: list[str] | None = None,
        min_rating: float | None = None,
        location_restriction: GeoRectangle | None = None,
        location_bias: GeoRectangle | None = None,
    ) -> list[Place]:
        """텍스트 쿼리로 장소를 검색합니다."""
        if not query.strip():
            return []
        if location_restriction is not None and location_bias is not None:
            raise ValueError("locationRestriction과 locationBias는 동시에 사용할 수 없습니다.")

        payload: dict[str, Any] = {"textQuery": query, "pageSize": self._page_size}
        if self._language_code:
            payload["languageCode"] = self._language_code
        if min_rating is not None:
            payload["minRating"] = min(5.0, max(0.0, float(min_rating)))
        if price_levels:
            normalized_levels = [str(level).strip() for level in price_levels if str(level).strip()]
            if normalized_levels:
                payload["priceLevels"] = normalized_levels
        if location_restriction is not None:
            payload["locationRestriction"] = location_restriction.to_google_location_restriction_payload()
        elif location_bias is not None:
            payload["locationBias"] = location_bias.to_google_location_bias_payload()

        data = await self._request(
            method="POST",
            url=f"{self._BASE_URL}{self._SEARCH_PATH}",
            payload=payload,
            params=None,
            field_mask=self._SEARCH_FIELD_MASK,
        )

        places_raw = (data or {}).get("places", [])
        places = [place for place in (self._map_place(item) for item in places_raw) if place]
        logger.info(
            (
                "Google Places search completed: min_rating_applied=%s "
                "geo_filter_applied=%s geo_filter_type=%s geo_bias_applied=%s candidate_count=%d"
            ),
            min_rating is not None,
            location_restriction is not None,
            "bbox" if location_restriction is not None else "none",
            location_bias is not None,
            len(places),
        )
        return places

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
        request_timeout = to_requests_timeout(self._timeout_seconds)

        def _send() -> requests.Response:
            with requests.Session() as session:
                return session.request(
                    method=method,
                    url=url,
                    json=payload,
                    params=params,
                    headers=headers,
                    timeout=request_timeout,
                )

        try:
            response = await asyncio.to_thread(_send)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response else None
            body = (response.text or "")[:200] if response else ""
            logger.error("Google Places API error: status=%s body=%s", status_code, body)
            return None
        except requests.RequestException as exc:
            logger.error("Google Places API request failed: %s", exc)
            return None
        except ValueError as exc:
            logger.error("Google Places API response parse failed: %s", exc)
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
            types=raw.get("types") or [],
        )


@lru_cache(maxsize=1)
def get_google_places_service() -> GooglePlacesService:
    """설정 재사용을 위한 프로세스 단위 싱글톤을 반환합니다."""
    return GooglePlacesService.from_settings()
