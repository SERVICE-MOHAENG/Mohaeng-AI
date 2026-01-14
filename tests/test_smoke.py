from app.main import create_graph


def test_graph_invocation():
    """
    [스모크 테스트]
    그래프가 정상적으로 생성되고, invoke 호출 시 에러 없이 결과(dict)를 반환하는지 확인
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
