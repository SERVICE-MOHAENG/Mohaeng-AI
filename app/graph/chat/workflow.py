"""로드맵 대화 그래프 워크플로우 구성."""

from langgraph.graph import END, StateGraph

from app.graph.chat.nodes import analyze_intent, cascade, mutate, respond
from app.graph.chat.state import ChatState
from app.schemas.enums import ChatStatus


def _route_after_intent(state: ChatState) -> str:
    """의도 분석 결과에 따라 다음 노드를 결정합니다."""
    if state.get("error"):
        return "respond"
    if state.get("status") == ChatStatus.ASK_CLARIFICATION:
        return "respond"
    return "mutate"


def _route_after_mutate(state: ChatState) -> str:
    """mutate 결과에 따라 다음 노드를 결정합니다."""
    if state.get("error"):
        return "respond"
    if state.get("status") == ChatStatus.ASK_CLARIFICATION:
        return "respond"
    return "cascade"


def _create_chat_workflow() -> StateGraph:
    """로드맵 대화 그래프 워크플로우를 생성합니다."""
    workflow = StateGraph(ChatState)

    workflow.add_node("analyze_intent", analyze_intent)
    workflow.add_node("mutate", mutate)
    workflow.add_node("cascade", cascade)
    workflow.add_node("respond", respond)

    workflow.set_entry_point("analyze_intent")
    workflow.add_conditional_edges("analyze_intent", _route_after_intent, ["mutate", "respond"])
    workflow.add_conditional_edges("mutate", _route_after_mutate, ["cascade", "respond"])
    workflow.add_edge("cascade", "respond")
    workflow.add_edge("respond", END)

    return workflow


compiled_chat_graph = _create_chat_workflow().compile()
