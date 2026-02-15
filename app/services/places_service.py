"""Places 서비스 프로토콜."""

from abc import ABC, abstractmethod

from app.core.geo import GeoRectangle
from app.schemas.place import Place


class PlacesServiceProtocol(ABC):
    """Places 제공자 공통 인터페이스."""

    @abstractmethod
    async def search(
        self,
        query: str,
        price_levels: list[str] | None = None,
        min_rating: float | None = None,
        location_restriction: GeoRectangle | None = None,
        location_bias: GeoRectangle | None = None,
    ) -> list[Place]:
        """검색어로 장소를 조회합니다."""
        raise NotImplementedError

    @abstractmethod
    async def details(self, place_id: str) -> Place | None:
        """place_id로 장소 상세를 조회합니다."""
        raise NotImplementedError
