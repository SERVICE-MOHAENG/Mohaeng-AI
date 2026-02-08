"""추천 그래프 워크플로우 구성."""

from langgraph.graph import END, StateGraph

from app.graph.recommendation.nodes import (
    generate_recommendations,
    rerank_regions,
    search_regions,
    transform_input,
)
from app.graph.recommendation.state import GraphState


def _create_workflow() -> StateGraph:
    """추천 그래프 워크플로우를 생성합니다."""
    workflow = StateGraph(GraphState)

    workflow.add_node("transform_input", transform_input)
    workflow.add_node("search_regions", search_regions)
    workflow.add_node("rerank_regions", rerank_regions)
    workflow.add_node("generate_recommendations", generate_recommendations)

    workflow.set_entry_point("transform_input")
    workflow.add_edge("transform_input", "search_regions")
    workflow.add_edge("search_regions", "rerank_regions")
    workflow.add_edge("rerank_regions", "generate_recommendations")
    workflow.add_edge("generate_recommendations", END)

    return workflow


compiled_graph = _create_workflow().compile()
