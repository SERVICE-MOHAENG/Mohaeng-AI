"""`LangGraph` 워크플로우 구성."""

from langgraph.graph import END, StateGraph

from app.core.logger import get_logger
from app.graph.nodes import (
    generate_recommendations,
    rerank_regions,
    search_regions,
    transform_input,
)
from app.graph.state import GraphState

logger = get_logger(__name__)


def _create_workflow() -> StateGraph:
    """`LangGraph` 워크플로우를 생성합니다."""
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
