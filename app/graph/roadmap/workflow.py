"""로드맵 그래프 워크플로우 구성."""

from langgraph.graph import END, StateGraph

from app.graph.roadmap.nodes import (
    fetch_places_from_slots,
    generate_skeleton,
    synthesize_final_roadmap,
)
from app.graph.roadmap.state import RoadmapState


def _create_roadmap_workflow() -> StateGraph:
    """로드맵 그래프 워크플로우를 생성합니다."""
    workflow = StateGraph(RoadmapState)

    workflow.add_node("generate_skeleton", generate_skeleton)
    workflow.add_node("fetch_places_from_slots", fetch_places_from_slots)
    workflow.add_node("synthesize_final_roadmap", synthesize_final_roadmap)

    workflow.set_entry_point("generate_skeleton")
    workflow.add_edge("generate_skeleton", "fetch_places_from_slots")
    workflow.add_edge("fetch_places_from_slots", "synthesize_final_roadmap")
    workflow.add_edge("synthesize_final_roadmap", END)

    return workflow


compiled_roadmap_graph = _create_roadmap_workflow().compile()
