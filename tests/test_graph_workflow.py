"""LangGraph 워크플로우 테스트."""

from app.graph.nodes import transform_input
from app.graph.state import GraphState


class TestTransformInput:
    """transform_input 노드 테스트."""

    def test_transform_with_interests(self):
        """관심사가 포함된 쿼리 변환 테스트."""
        state: GraphState = {
            "user_preference": {
                "main_interests": ["HISTORY", "FOOD"],
            },
            "top_k": 3,
        }

        result = transform_input(state)

        assert "transformed_query" in result
        assert "역사와 문화 유적" in result["transformed_query"]
        assert "맛집과 음식 문화" in result["transformed_query"]

    def test_transform_with_travel_range(self):
        """여행 거리가 포함된 쿼리 변환 테스트."""
        state: GraphState = {
            "user_preference": {
                "travel_range": "DOMESTIC",
            },
            "top_k": 3,
        }

        result = transform_input(state)

        assert "transformed_query" in result
        assert "국내 여행" in result["transformed_query"]

    def test_transform_with_environment(self):
        """환경 선호가 포함된 쿼리 변환 테스트."""
        state: GraphState = {
            "user_preference": {
                "environment": "COASTAL",
            },
            "top_k": 3,
        }

        result = transform_input(state)

        assert "transformed_query" in result
        assert "해안가와 바다" in result["transformed_query"]

    def test_transform_empty_preference(self):
        """빈 선호도일 때 기본 쿼리 생성 테스트."""
        state: GraphState = {
            "user_preference": {},
            "top_k": 3,
        }

        result = transform_input(state)

        assert "transformed_query" in result
        assert "인기 있는 여행지 추천" in result["transformed_query"]

    def test_transform_full_preference(self):
        """모든 선호도가 포함된 쿼리 변환 테스트."""
        state: GraphState = {
            "user_preference": {
                "travel_range": "EUROPE",
                "budget_level": "HIGH",
                "main_interests": ["HISTORY", "NATURE"],
                "environment": "URBAN",
                "weather": "COOL",
            },
            "top_k": 5,
        }

        result = transform_input(state)

        assert "transformed_query" in result
        assert "유럽" in result["transformed_query"]
        assert "역사와 문화 유적" in result["transformed_query"]
        assert "도시적인 분위기" in result["transformed_query"]
        assert "시원한 날씨" in result["transformed_query"]
