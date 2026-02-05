"""Places 서비스 추상 프로토콜 정의."""

from abc import ABC, abstractmethod

from app.schemas.place import Place


class PlacesServiceProtocol(ABC):
    """Places 서비스 추상 베이스 클래스.

    Google Places API 또는 Mock 서비스가 구현해야 하는 인터페이스를 정의한다.
    """

    MIN_RATING: float = 4.0
    MIN_REVIEWS: int = 100

    @abstractmethod
    async def search(self, query: str) -> list[Place]:
        """검색 쿼리로 장소를 검색한다.

        Args:
            query: 검색 쿼리 (예: "Asakusa Sightseeing")

        Returns:
            품질 필터링이 적용된 장소 목록
        """
        pass
