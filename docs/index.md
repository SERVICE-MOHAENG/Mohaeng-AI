---
title: "Mohaeng-AI 문서 맵"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [docs, agent, template]
ai_action: "reference-only"
---

# Mohaeng-AI Knowledge Map

이 문서는 Mohaeng-AI 프로젝트의 문서 체계와 작성 규칙을 정리한 진입점입니다. 새 문서를 만들거나 기존 문서를 수정하는 에이전트는 먼저 이 문서를 확인하고, 각 하위 문서의 목적에 맞는 위치에 내용을 추가해야 합니다.

## 문서 구조

| 경로 | 용도 | 작성 기준 |
| --- | --- | --- |
| `docs/api/` | API 명세 | AI 에이전트가 참조할 엔드포인트 정의 및 통신 규격 |
| `docs/architecture/` | 설계와 기술 결정 | 모듈 경계, 데이터 흐름, 주요 설계 선택의 근거를 정리 |
| `docs/context/` | 프로젝트 배경과 현재 맥락 | 왜 이 기능이 필요한지, 현재 어떤 제약이 있는지 기록 |
| `docs/decisions/` | 의사결정 기록 | 대안 비교, 선택 이유, 후속 영향 등을 ADR 형태로 남김 |
| `docs/guides/` | 작업 가이드 | 반복 작업, 운영 절차, 구현 패턴, 체크리스트를 문서화 |
| `docs/specs/` | 기능 명세 | 구현 대상, 요구사항, 입력/출력, 예외 조건을 정의 |


## 문서 작성 규칙

1. 모든 문서는 YAML frontmatter로 시작합니다.
2. 기본 필드는 `title`, `status`, `author`, `created_at`, `tags`, `ai_action`입니다.
3. `status`는 다음 값을 사용합니다.
   - `draft`: 초안
   - `review`: 검토 필요
   - `approved`: 승인됨
4. `ai_action`은 다음 기준으로 설정합니다.
   - `editable`: AI가 직접 수정해도 되는 문서
   - `reference-only`: 참고용으로만 읽고 수정하지 않는 문서
5. 제목은 문서의 목적이 한눈에 보이도록 작성합니다.
6. 태그는 검색 가능성을 높이기 위해 최소 2개 이상 구체적으로 작성합니다.
7. 날짜는 `YYYY-MM-DD` 형식으로 통일합니다.
8. 본문은 짧은 요약, 상세 내용, 필요 시 체크리스트 순서로 구성합니다.

## 템플릿 사용 규칙

- 새 문서를 만들 때는 `docs/TEMPLATE.md`를 복사해 시작합니다.
- 템플릿의 `status`가 `draft`인 문서는 구현 기준 문서로 사용하지 않습니다.
- 문서가 구현 기준으로 충분히 검토되면 `status`를 `approved`로 바꿉니다.
- AI가 문서를 수정할 때는 frontmatter를 임의로 바꾸지 말고, 필요한 경우만 최소 수정합니다.
- 문서 내용이 코드와 충돌하면 코드를 우선 확인하고, 문서를 코드 상태에 맞게 갱신합니다.

## 에이전트 작업 원칙

- 코드 작성이나 수정 전에 관련 문서를 먼저 확인합니다.
- 구현 범위가 넓으면 `specs -> architecture -> guides` 순서로 읽습니다.
- 기존 문서와 중복되는 새 파일을 만들지 말고, 먼저 적절한 기존 문서가 있는지 확인합니다.
- 문서 수정 후에는 관련 코드, 테스트, 설정과의 일치 여부를 점검합니다.
- 승인되지 않은 문서는 추측으로 완성하지 말고, 부족한 정보는 `TODO`로 명시합니다.

## AI Agent 작업 시작 가이드

배경 컨텍스트가 없는 에이전트는 다음 순서로 작업을 시작합니다.

1. 이 문서를 읽고 문서 구조와 작업 규칙을 확인합니다.
2. 작업 대상 기능의 `specs` 문서를 읽어 기능 동작과 제약을 파악합니다.
3. 외부 계약이 바뀌는 작업이면 `api` 문서를 함께 확인합니다.
4. 서버 간 흐름, callback, 비동기 처리에 영향이 있으면 `architecture` 문서를 확인합니다.
5. 코드 변경 전에는 관련 코드 진입점과 테스트 파일을 확인합니다.
6. 문서와 코드가 충돌하면 코드를 우선 확인하고, 문서를 현재 구현에 맞게 갱신합니다.

### 기능별 작업 맵

| 작업 대상 | 먼저 읽을 문서 | 주요 코드 진입점 | 관련 테스트 |
| --- | --- | --- | --- |
| 여행지 추천 | [설문 기반 여행지 추천 기능](specs/recommend-destinations.md), [여행지 추천 API](api/recommend-api.md), [여행지 추천 서버 간 통신 구조](architecture/recommend-server-communication.md) | `app/api/recommend.py`, `app/services/recommend_service.py`, `app/schemas/recommend.py`, `app/schemas/enums.py` | `tests/test_recommend_service.py` |
| 로드맵 생성 | [로드맵 생성 기능](specs/roadmap-generation.md), [로드맵 생성 API](api/generate-api.md), [로드맵 생성 서버 간 통신 구조](architecture/roadmap-generation-server-communication.md), [로드맵 생성 ADR](decisions/roadmap-generation-ai-pipeline.md) | `app/api/generate.py`, `app/services/generate_service.py`, `app/graph/roadmap/`, `app/services/google_places_service.py`, `app/services/places_service.py`, `app/schemas/generate.py`, `app/schemas/course.py` | `tests/test_roadmap_place_name_translation.py` |
| 로드맵 채팅 수정 | [로드맵 채팅 수정 기능](specs/roadmap-chat-modification.md), [로드맵 채팅 API](api/chat-api.md), [로드맵 채팅 수정 서버 간 통신 구조](architecture/roadmap-chat-server-communication.md) | `app/api/chat.py`, `app/services/chat_service.py`, `app/graph/chat/`, `app/schemas/chat.py`, `app/schemas/course.py` | `tests/test_chat_schema.py` |
| callback 전송 | 각 기능 API 문서, 각 서버 간 통신 구조 문서 | `app/services/callback_delivery.py`, `app/services/callback_url.py` | `tests/test_callback_delivery.py`, `tests/test_callback_url.py` |
| readiness / healthcheck | [헬스체크 API](api/health-api.md), [기술 스택](architecture/technology-stack.md) | `app/main.py`, `app/core/readiness.py`, `app/core/config.py` | `tests/test_main.py`, `tests/test_readiness.py` |
| LLM 모델 라우팅과 알림 | [기술 스택](architecture/technology-stack.md), [AI 개발팀 협업 가이드](guides/collaboration-guide.md) | `app/core/llm_router.py`, `app/services/webhook_notification.py` | `tests/test_llm_router_webhooks.py`, `tests/test_webhook_notification.py` |

## 빠른 이동

### 문서 영역

- 프로젝트 개요: [모행 프로젝트 개요](context/project-overview.md)
- 웹훅 이벤트 목록: [Mohaeng-AI 웹훅 이벤트 목록](context/webhook-events.md)
- 시장 문제와 타겟 사용자: [시장 문제와 타겟 사용자](context/market-and-target-users.md)
- 기술 스택: [기술 스택](architecture/technology-stack.md)
- 협업 가이드: [AI 개발팀 협업 가이드](guides/collaboration-guide.md)
- Git 커밋 컨벤션: [Git 커밋 컨벤션](guides/git-commit-convention.md)

### 기능별 문서 흐름

| 기능 | 맥락/결정 | 기능 명세 | API | 서버 통신 |
| --- | --- | --- | --- | --- |
| 여행지 추천 | [시장 문제와 타겟 사용자](context/market-and-target-users.md) | [설문 기반 여행지 추천 기능](specs/recommend-destinations.md) | [여행지 추천 API](api/recommend-api.md) | [여행지 추천 서버 간 통신 구조](architecture/recommend-server-communication.md) |
| 로드맵 생성 | [여행 일정 생성을 위한 AI 파이프라인 및 데이터 소스 선정](decisions/roadmap-generation-ai-pipeline.md) | [로드맵 생성 기능](specs/roadmap-generation.md) | [로드맵 생성 API](api/generate-api.md) | [로드맵 생성 서버 간 통신 구조](architecture/roadmap-generation-server-communication.md) |
| 로드맵 채팅 수정 | [모행 프로젝트 개요](context/project-overview.md) | [로드맵 채팅 수정 기능](specs/roadmap-chat-modification.md) | [로드맵 채팅 API](api/chat-api.md) | [로드맵 채팅 수정 서버 간 통신 구조](architecture/roadmap-chat-server-communication.md) |

### API와 운영

- [헬스체크 API](api/health-api.md)
- [로드맵 AI 파이프라인 대안 목록](decisions/roadmap-generation-ai-pipeline-alternatives.md)
