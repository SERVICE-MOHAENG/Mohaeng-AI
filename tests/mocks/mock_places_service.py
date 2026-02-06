"""Google Places API Mock 서비스.

실제 API 호출 없이 샘플 Place 데이터를 반환하는 Mock 서비스.
Stage 1 개발 및 테스트용으로 사용된다.
"""

from app.schemas.place import Place, PlaceGeometry
from app.services.places_service import PlacesServiceProtocol


class MockGooglePlacesService(PlacesServiceProtocol):
    """Mock Google Places 서비스.

    실제 API 호출 없이 미리 정의된 샘플 데이터를 반환한다.
    품질 필터링 조건: 평점 4.0 이상, 리뷰 100개 이상.
    """

    MIN_RATING: float = 4.0
    MIN_REVIEWS: int = 100

    # 지역별 샘플 장소 데이터
    _SAMPLE_PLACES: dict[str, list[dict]] = {
        "asakusa": [
            {
                "place_id": "ChIJ8T1GpMGOGGARDYGSgpooDWw",
                "name": "센소지",
                "address": "2-3-1 Asakusa, Taito City, Tokyo",
                "latitude": 35.7148,
                "longitude": 139.7967,
                "rating": 4.6,
                "user_ratings_total": 89542,
                "types": ["tourist_attraction", "place_of_worship"],
            },
            {
                "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
                "name": "나카미세 상점가",
                "address": "1-36-3 Asakusa, Taito City, Tokyo",
                "latitude": 35.7122,
                "longitude": 139.7947,
                "rating": 4.3,
                "user_ratings_total": 45231,
                "types": ["shopping_mall", "tourist_attraction"],
            },
            {
                "place_id": "ChIJ5RXqLcGOGGARR1zuI2L2SR8",
                "name": "아사쿠사 문화 관광 정보 센터",
                "address": "2-18-9 Kaminarimon, Taito City, Tokyo",
                "latitude": 35.7109,
                "longitude": 139.7966,
                "rating": 4.4,
                "user_ratings_total": 12340,
                "types": ["tourist_attraction", "point_of_interest"],
            },
        ],
        "shibuya": [
            {
                "place_id": "ChIJFfySZNeMGGARab2Cwm7AUbs",
                "name": "시부야 스크램블 교차로",
                "address": "Shibuya, Tokyo",
                "latitude": 35.6595,
                "longitude": 139.7004,
                "rating": 4.5,
                "user_ratings_total": 67890,
                "types": ["tourist_attraction", "point_of_interest"],
            },
            {
                "place_id": "ChIJFfySZNeMGGARab2Cwm7AU00",
                "name": "하치코 동상",
                "address": "Shibuya Station, Shibuya, Tokyo",
                "latitude": 35.659,
                "longitude": 139.7006,
                "rating": 4.4,
                "user_ratings_total": 34567,
                "types": ["monument", "tourist_attraction"],
            },
        ],
        "shinjuku": [
            {
                "place_id": "ChIJFfySZNeMGGARab2Cwm8AUbs",
                "name": "신주쿠 교엔",
                "address": "11 Naitomachi, Shinjuku City, Tokyo",
                "latitude": 35.6852,
                "longitude": 139.7100,
                "rating": 4.6,
                "user_ratings_total": 56789,
                "types": ["park", "tourist_attraction"],
            },
        ],
    }

    async def search(self, query: str) -> list[Place]:
        """검색 쿼리로 장소를 검색한다.

        Args:
            query: 검색 쿼리 (예: "Asakusa Sightseeing")

        Returns:
            품질 필터링이 적용된 장소 목록
        """
        query_lower = query.lower()
        places: list[Place] = []

        # 쿼리에서 매칭되는 지역의 샘플 데이터 반환
        for area_key, sample_list in self._SAMPLE_PLACES.items():
            if area_key in query_lower:
                for sample in sample_list:
                    places.append(
                        Place(
                            place_id=sample["place_id"],
                            name=sample["name"],
                            address=sample["address"],
                            geometry=PlaceGeometry(
                                latitude=sample["latitude"],
                                longitude=sample["longitude"],
                            ),
                            rating=sample["rating"],
                            user_ratings_total=sample["user_ratings_total"],
                            types=sample["types"],
                            photo_reference=f"mock_photo_{sample['place_id'][-8:]}",
                        )
                    )
                break

        # 매칭되는 지역이 없으면 기본 샘플 데이터 생성
        if not places:
            places = self._generate_default_places(query)

        filtered = self._filter_by_quality(places)
        return self._select_top_one(filtered)

    def _generate_default_places(self, query: str) -> list[Place]:
        """기본 샘플 장소 데이터를 생성한다."""
        return [
            Place(
                place_id=f"mock_{query.replace(' ', '_')}_{i}",
                name=f"{query} 추천 장소 {i}",
                address=f"{query} 지역 주소 {i}",
                geometry=PlaceGeometry(
                    latitude=35.6762 + i * 0.01,
                    longitude=139.6503 + i * 0.01,
                ),
                rating=4.0 + (i % 10) * 0.1,
                user_ratings_total=100 + i * 50,
                types=["tourist_attraction", "point_of_interest"],
                photo_reference=f"mock_photo_default_{i}",
            )
            for i in range(1, 4)
        ]

    def _filter_by_quality(self, places: list[Place]) -> list[Place]:
        """평점 4.0 이상, 리뷰 100개 이상인 장소만 필터링한다."""
        return [
            place
            for place in places
            if place.rating >= self.MIN_RATING and place.user_ratings_total >= self.MIN_REVIEWS
        ]

    def _select_top_one(self, places: list[Place]) -> list[Place]:
        """평점 최고, 동점 시 리뷰 수 최다인 장소 1개를 선택한다."""
        if not places:
            return []
        sorted_places = sorted(
            places,
            key=lambda p: (p.rating, p.user_ratings_total),
            reverse=True,
        )
        return [sorted_places[0]]
