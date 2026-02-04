"""로드맵 그래프 워크플로우 정의."""

from langgraph.graph import END, StateGraph

from app.graph.roadmap.nodes import generate_skeleton
from app.graph.roadmap.state import RoadmapState


def _create_roadmap_workflow() -> StateGraph:
    workflow = StateGraph(RoadmapState)

    workflow.add_node("generate_skeleton", generate_skeleton)
    workflow.set_entry_point("generate_skeleton")
    workflow.add_edge("generate_skeleton", END)

    return workflow


compiled_roadmap_graph = _create_roadmap_workflow().compile()
