"""LangGraph 워크플로우 테스트."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.graph.nodes import rerank_regions, transform_input
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


class TestRerankRegions:
    """rerank_regions 노드 테스트."""

    @patch("app.graph.nodes.llm")
    def test_rerank_with_low_budget(self, mock_llm: MagicMock):
        """LOW 예산 시 물가 저렴한 지역 우선 테스트."""
        mock_response = MagicMock()
        mock_response.content = """[
            {"region_name": "방콕", "constraints_met": true, "score": 0.9, "reason": "물가 저렴"},
            {"region_name": "파리", "constraints_met": false, "score": 0.3, "reason": "물가 높음"}
        ]"""
        mock_llm.invoke.return_value = mock_response

        state: GraphState = {
            "user_preference": {"budget_level": "LOW"},
            "candidates": [
                {"region_id": uuid4(), "region_name": "방콕", "score": 0.8},
                {"region_id": uuid4(), "region_name": "파리", "score": 0.8},
            ],
        }

        result = rerank_regions(state)

        assert "ranked_regions" in result
        assert len(result["ranked_regions"]) == 2
        assert result["ranked_regions"][0]["region_name"] == "방콕"
        assert result["ranked_regions"][0]["constraints_met"] is True

    @patch("app.graph.nodes.llm")
    def test_rerank_with_high_budget(self, mock_llm: MagicMock):
        """HIGH 예산 시 대부분 지역 추천 가능 테스트."""
        mock_response = MagicMock()
        mock_response.content = """[
            {"region_name": "파리", "constraints_met": true, "score": 0.9, "reason": "적합"},
            {"region_name": "방콕", "constraints_met": true, "score": 0.8, "reason": "적합"}
        ]"""
        mock_llm.invoke.return_value = mock_response

        state: GraphState = {
            "user_preference": {"budget_level": "HIGH"},
            "candidates": [
                {"region_id": uuid4(), "region_name": "파리", "score": 0.8},
                {"region_id": uuid4(), "region_name": "방콕", "score": 0.8},
            ],
        }

        result = rerank_regions(state)

        assert "ranked_regions" in result
        assert all(r["constraints_met"] for r in result["ranked_regions"])

    @patch("app.graph.nodes.llm")
    def test_rerank_empty_candidates(self, mock_llm: MagicMock):
        """빈 후보 목록 테스트."""
        state: GraphState = {
            "user_preference": {"budget_level": "LOW"},
            "candidates": [],
        }

        result = rerank_regions(state)

        assert result["ranked_regions"] == []
        mock_llm.invoke.assert_not_called()
