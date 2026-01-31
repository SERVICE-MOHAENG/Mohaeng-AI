"""LangGraph 워크플로우 구성."""

from functools import partial

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.graph.nodes import (
    generate_recommendations,
    rerank_regions,
    search_regions,
    transform_input,
)
from app.graph.state import GraphState

logger = get_logger(__name__)


def create_workflow(db: Session) -> StateGraph:
    """LangGraph 워크플로우를 생성합니다."""
    workflow = StateGraph(GraphState)

    workflow.add_node("transform_input", transform_input)
    workflow.add_node("search_regions", partial(search_regions, db=db))
    workflow.add_node("rerank_regions", rerank_regions)
    workflow.add_node("generate_recommendations", generate_recommendations)

    workflow.set_entry_point("transform_input")
    workflow.add_edge("transform_input", "search_regions")
    workflow.add_edge("search_regions", "rerank_regions")
    workflow.add_edge("rerank_regions", "generate_recommendations")
    workflow.add_edge("generate_recommendations", END)

    return workflow


def compile_workflow(db: Session):
    """워크플로우를 컴파일하여 실행 가능한 그래프를 반환합니다."""
    workflow = create_workflow(db)
    return workflow.compile()
