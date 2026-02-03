"""`LangGraph` 워크플로우를 수동으로 실행해 보는 테스트 스크립트."""

import logging
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger("Mohaeng")


class AgentState(TypedDict):
    """`LangGraph`의 상태를 정의하는 `TypedDict`."""

    query: str
    answer: NotRequired[str]


def call_fake_llm_node(state: AgentState) -> dict:
    """실제 `LLM` 호출을 모방하는 테스트용 노드."""
    fake_response = f"'{state['query']}'에 대한 추천 결과입니다. (API 키 없이 작동 중)"
    return {"answer": fake_response}


def create_graph() -> StateGraph:
    """테스트용 `LangGraph` 워크플로우를 생성하고 컴파일한다."""
    workflow = StateGraph(AgentState)
    workflow.add_node("guide", call_fake_llm_node)
    workflow.add_edge(START, "guide")
    workflow.add_edge("guide", END)
    return workflow.compile()


def main() -> None:
    """스크립트를 직접 실행할 때의 진입점."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    app = create_graph()
    user_input = {"query": "부산 맛집"}
    logger.info("📥 INPUT: %s", user_input["query"])
    result = app.invoke(user_input)
    logger.info("📤 OUTPUT: %s", result["answer"])


if __name__ == "__main__":
    main()
