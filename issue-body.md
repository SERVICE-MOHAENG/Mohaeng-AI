## 1. 개요 (Background)
서비스 디스코드 웹훅에서 LLM fallback 실패 제목이 영어로 남아 있고, JSON 본문과 스택 트레이스가 일반 텍스트로 표시되어 가독성이 떨어집니다.

## 2. 상세 내용 (Details)
- `llm_fallback_failed` 제목을 한국어로 통일합니다.
- JSON body와 stack trace 등 코드 성격의 값은 코드블록으로 감싸서 표시합니다.
- 채팅/생성/추천/LLM 라우터의 실패 웹훅 표현을 함께 정리합니다.
- 관련 테스트와 문서를 갱신합니다.

## 3. 할 일 목록 (To-Do)
- [x] LLM fallback 실패 제목 한국어화
- [x] JSON body / stack trace 코드블록 포맷 헬퍼 추가
- [x] 채팅/생성/추천 웹훅 포맷 적용
- [x] 테스트 추가/수정
- [x] 웹훅 문서 갱신

## 4. 완료 조건 (Definition of Done)
- [x] fallback 실패 웹훅 제목이 한국어로 표시된다.
- [x] JSON body와 stack trace가 코드블록으로 표시된다.
- [x] 관련 테스트가 통과한다.
- [x] 문서가 현재 구현과 일치한다.

## 5. 참고 자료 (References)
- `app/services/webhook_notification.py`
- `app/core/llm_router.py`
- `app/services/chat_service.py`
- `app/services/generate_service.py`
- `app/services/recommend_service.py`
- `tests/test_webhook_notification.py`
- `tests/test_llm_router_webhooks.py`
- `docs/context/webhook-events.md`
