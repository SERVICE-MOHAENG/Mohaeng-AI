from app.test_graph import create_graph


def test_graph_invocation():
    """LangGraph 객체의 생성 및 호출을 검증하는 스모크 테스트.

    이 테스트는 `create_graph` 함수가 유효한 LangGraph 실행 객체를 생성하는지,
    그리고 생성된 객체의 `invoke` 메서드가 에러 없이 정상적으로 호출되어
    예상된 형식의 결과를 반환하는지 확인합니다.

    주요 검증 항목:
    - `invoke` 메서드의 반환값이 딕셔너리(dict) 타입이어야 합니다.
    - 반환된 딕셔너리에 'answer' 키가 포함되어야 합니다.
    - 'answer' 키에 해당하는 값이 비어 있지 않아야 합니다.
    """
    # 1. 그래프(앱) 생성
    app = create_graph()

    # 2. 테스트 입력 데이터
    test_input = {"query": "테스트 실행"}

    # 3. 실행 (Invoke)
    result = app.invoke(test_input)

    # 4. 검증 (Assertion)
    # - 결과가 딕셔너리 타입인가?
    assert isinstance(result, dict), "결과는 딕셔너리(dict) 형태여야 합니다."
    # - 결과에 'answer' 키가 포함되어 있는가?
    assert "answer" in result, "결과에 'answer' 키가 있어야 합니다."
    # - (선택) 답변이 비어있지 않은가?
    assert len(result["answer"]) > 0, "답변 내용이 비어있으면 안 됩니다."
