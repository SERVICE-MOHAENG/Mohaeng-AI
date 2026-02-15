"""Places 서비스 추상 프로토콜 정의."""

from abc import ABC, abstractmethod

from app.schemas.place import Place


class PlacesServiceProtocol(ABC):
    """Places API 호출을 위한 인터페이스를 정의합니다."""

    @abstractmethod
    async def search(
        self,
        query: str,
        price_levels: list[str] | None = None,
        min_rating: float | None = None,
    ) -> list[Place]:
        """검색 쿼리로 장소를 검색합니다.

        Args:
            query: 검색 쿼리
            price_levels: Google Places priceLevels 필터 값 목록
            min_rating: Google Places minRating 필터 값 (None이면 미적용)

        Returns:
            검색 조건이 적용된 장소 목록
        """
        raise NotImplementedError

    @abstractmethod
    async def details(self, place_id: str) -> Place | None:
        """장소 상세 정보를 조회합니다.

        Args:
            place_id: Google Places ID

        Returns:
            장소 상세 정보 또는 None
        """
        raise NotImplementedError
