import logging  # [추가 1] 모듈 임포트
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

# ==========================================
# [Step 0] 로거 가져오기
# ==========================================
logger = logging.getLogger("Mohaeng")


# ==========================================
# [Step 1] State 정의
# ==========================================
class AgentState(TypedDict):
    query: str
    answer: NotRequired[str]


# ==========================================
# [Step 2] 노드 정의 (Mock)
# ==========================================
def call_fake_llm_node(state: AgentState):
    # 내부 디버깅용 로그 (선택 사항)
    # logger.info(f"노드 실행 중... 질문: {state['query']}")

    fake_response = f"'{state['query']}'에 대한 추천 결과입니다. (API 키 없이 작동 중)"
    return {"answer": fake_response}


# ==========================================
# [Step 3] 그래프 구성
# ==========================================
def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("guide", call_fake_llm_node)
    workflow.add_edge(START, "guide")
    workflow.add_edge("guide", END)
    return workflow.compile()


# ==========================================
# [실행부]
# ==========================================
if __name__ == "__main__":
    # ==========================================
    # 로깅 기본 설정 (실행 시에만 적용)
    # ==========================================
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    # 그래프 생성
    app = create_graph()

    # 테스트 데이터
    user_input = {"query": "부산 맛집"}

    # [추가 2] 실행 전 입력 로그 (1줄)
    logger.info(f"📥 INPUT: {user_input['query']}")

    # 실행
    result = app.invoke(user_input)

    # [추가 3] 실행 후 출력 로그 (1줄)
    logger.info(f"📤 OUTPUT: {result['answer']}")
