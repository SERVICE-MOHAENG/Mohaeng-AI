---
title: "로드맵 채팅 수정 기능"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [specs, roadmap, chat, modification, langgraph]
ai_action: "editable"
---

# 요약

로드맵 채팅 수정 기능은 사용자의 자연어 요청을 분석해 기존 로드맵을 수정하거나, 수정이 아닌 일반 질문에 답변합니다.
API는 `/api/v1/chat`이며, 요청을 즉시 수락한 뒤 LangGraph 기반 대화 파이프라인을 비동기로 실행하고 콜백으로 결과를 전달합니다.
현재 지원하는 수정 작업은 장소 교체, 추가, 삭제, 같은 일자 내 순서 이동, 단일 일차 동선 최적화, 일차 간 장소 이동, 일차 일정 묶음 교체입니다.

# 배경

초기 생성된 로드맵은 사용자의 추가 요청이나 취향 변화에 따라 수정될 수 있어야 합니다.
사용자가 JSON 구조를 직접 편집하지 않고 자연어로 요청하면, 시스템은 의도를 분석하고 현재 로드맵의 구조를 유지한 채 필요한 부분만 변경합니다.
새로 추가되거나 교체되는 장소는 Google Places 검색 결과를 사용해 실제 장소 데이터와 좌표를 확보합니다.

# 본문

## API 경계

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /api/v1/chat` |
| 인증 | `x-service-secret` 헤더 필요 |
| 처리 방식 | 요청 접수 후 비동기 작업 실행 |
| 즉시 응답 | `ChatAckResponse` |
| 콜백 경로 | `{callback_url}/itineraries/{job_id}/chat-result` |

즉시 응답 예시는 다음과 같습니다.

```json
{
  "job_id": "modify-job-12345",
  "status": "ACCEPTED"
}
```

## 입력값

요청 모델은 `ChatRequest`입니다.

| 필드 | 타입 | 필수 여부 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | NestJS BullMQ 작업 ID |
| `callback_url` | URL | Yes | 결과를 받을 NestJS 콜백 URL |
| `current_itinerary` | `ChatRoadmap` | Yes | 현재 세션의 전체 로드맵 |
| `companion_type` | `CompanionType[]` | Yes | 동행자 유형 목록 |
| `travel_themes` | `TravelTheme[]` | Yes | 여행 테마 목록 |
| `pace_preference` | `PacePreference` | Yes | 일정 밀도 선호 |
| `planning_preference` | `PlanningPreference` | Yes | 계획 성향 |
| `destination_preference` | `DestinationPreference` | Yes | 관광지/로컬 선호 |
| `activity_preference` | `ActivityPreference` | Yes | 활동/휴식 선호 |
| `priority_preference` | `PriorityPreference` | Yes | 효율/감성 우선순위 |
| `user_query` | string | Yes | 사용자 발화 |
| `session_history` | `Message[]` | No | 최근 대화 맥락 |

`current_itinerary`는 `start_date`, `end_date`, `trip_days`, `nights`, `people_count`, `tags`, `title`, `summary`, `planning_preference`, `itinerary`를 포함해야 합니다.
`current_itinerary.itinerary[].places`는 공용 `DailyItinerary` 스키마 기준으로 하루 최소 1개, 최대 10개 장소를 포함해야 합니다.

## 처리 흐름

LangGraph 워크플로우는 다음 구조입니다.

```text
analyze_intent
├─ GENERAL_CHAT -> general_chat -> END
├─ REJECTED / ASK_CLARIFICATION -> respond -> END
└─ mutate -> propose_visit_time -> cascade -> respond -> END
```

### 1. `analyze_intent`

사용자 발화를 `GENERAL_CHAT` 또는 `MODIFICATION`으로 분류합니다.
수정 요청이면 `ChatIntent`를 추출합니다.

지원하는 operation은 다음과 같습니다.

| Operation | 설명 |
| --- | --- |
| `REPLACE` | 특정 일자의 특정 순서 장소를 다른 장소로 교체 |
| `ADD` | 특정 일자의 특정 위치에 새 장소 추가 |
| `REMOVE` | 특정 일자의 특정 순서 장소 삭제 |
| `MOVE` | 같은 일자 안 장소 위치 변경, 단일 일차 동선 최적화, 일차 간 장소 이동 |

`REPLACE`는 내부 `target_scope`로 장소 단위 교체와 일차 일정 묶음 교체를 구분합니다.
`MOVE`는 내부 `target_scope`로 장소 단위 이동과 단일 일차 동선 최적화(`DAY_OPTIMIZE`)를 구분합니다.
`target_scope=DAY_PLACES`이면 두 일차의 `places` 배열만 서로 교체하고, `day_number`, `daily_date` 등 day-level 메타데이터는 유지합니다.
`target_scope=DAY_OPTIMIZE`이면 해당 일차의 FOOD anchor를 유지한 채 나머지 장소 순서를 거리 기준으로 재정렬합니다.

의도 분석은 LLM을 우선 사용하고, 실패 시 수정 키워드와 일차/삭제 요청 감지 휴리스틱을 fallback으로 사용합니다.
REPLACE/ADD 검색어에는 현재 일자의 주소에서 추출한 지역 힌트를 강제로 포함합니다.

다음 요청은 제한됩니다.

- 일차 전체 삭제는 지원하지 않습니다.
- 일차 일정 묶음 교체는 지원하지만, 여행 날짜, 기간, 숙박 수 자체 변경은 지원하지 않습니다.
- 여러 일차 또는 전체 일정 동선 최적화는 현재 지원하지 않습니다.
- 삭제 대상이 모호하면 `ASK_CLARIFICATION`으로 전환합니다.
- 복합 요청은 현재 첫 번째 명확한 작업 중심으로 처리합니다.

### 2. `general_chat`

수정 요청이 아닌 일반 질문은 현재 로드맵 요약과 대화 맥락을 바탕으로 답변하고 종료합니다.
이 경우 로드맵 JSON은 변경하지 않습니다.

### 3. `mutate`

분석된 의도에 따라 `current_itinerary`를 복사한 뒤 실제 JSON 변경을 적용합니다.

수정 규칙은 다음과 같습니다.

- 하루 장소 수는 공용 `DailyItinerary` 스키마 기준으로 최소 1개, 최대 10개입니다.
- REPLACE/ADD는 Google Places 검색으로 실제 장소를 가져옵니다.
- REPLACE/ADD로 새로 들어온 장소에는 Google Places `primaryType`과 `types`를 내부 정적 매핑한 `place_category`를 포함합니다.
- 검색 시 현재 일자의 장소 좌표로 bbox를 만들고 10km margin을 적용합니다.
- bbox restriction, bbox bias, 지역명을 붙인 unfiltered 검색, 최소 평점 해제 검색 순으로 fallback합니다.
- LLM rerank가 켜져 있으면 후보 중 사용자 요청과 가장 맞는 장소를 선택합니다.
- 단일 일차 동선 최적화는 기존 `route_optimizer`를 재사용하며 FOOD anchor 간 상대 순서를 유지합니다.
- 일차 간 MOVE는 출발 일차가 최소 1개 장소를 유지하고 도착 일차가 최대 10개 장소를 넘지 않을 때만 처리합니다.
- 단일 일차 동선 최적화도 대상 일차의 `visit_sequence`를 1부터 재정렬합니다.
- 일차 간 MOVE와 일차 일정 묶음 교체는 영향을 받은 양쪽 일차의 `visit_sequence`를 1부터 재정렬합니다.
- `diff_keys`는 day 단위 key를 추가하지 않고, 영향을 받은 일차의 장소 카드 key를 `dayN_placeM` 형식으로 기록합니다.

### 4. `propose_visit_time`

`planning_preference == PLANNED`인 경우에만 수정된 일자의 장소 목록을 기준으로 LLM이 방문 시간 후보를 제안합니다.
LLM 제안은 다음 `cascade` 단계에서 형식, 허용 범위, 방문 순서 기준 시간 비감소 조건을 검증한 뒤 최종 `visit_time` 결정값으로 사용됩니다.
`SPONTANEOUS` 로드맵에서는 이 노드가 LLM을 호출하지 않고 빈 proposal을 반환합니다.

### 5. `cascade`

변경된 일자만 대상으로 방문 시간과 순서를 재정렬하고 제약을 검증합니다.
단일 일차 동선 최적화, 일차 간 MOVE, 일차 일정 묶음 교체처럼 하나 이상의 일차가 바뀌는 경우, `diff_keys`에서 추출한 모든 일차에 같은 정책을 적용합니다.
`planning_preference`가 `PLANNED`이면 `08:00` 이상 `24:00` 이하의 `HH:MM` 형식을 사용하고, LLM 제안이 누락되거나 유효하지 않은 구간은 서버 fallback으로 보정합니다.
`24:00`은 유효한 종료 시각으로 허용하지만 `24:01` 이상은 거부합니다.
`SPONTANEOUS`이면 LLM 제안 없이 section 기반 값을 사용합니다.
시간 검증, fallback, 경고 생성은 공용 visit time policy를 사용합니다.

### 6. `respond`

처리 결과를 사용자에게 보여줄 단일 메시지로 정리합니다.
성공, 반려, 추가 확인, 실패 상태에 맞게 `message`, `modified_itinerary`, `diff_keys`를 구성합니다.

## 출력값

콜백 페이로드는 상태에 따라 달라집니다.

성공 예시는 다음과 같습니다.

```json
{
  "status": "SUCCESS",
  "message": "1일차 2번째 장소를 새 장소로 변경했습니다.",
  "diff_keys": ["day1_place2"],
  "modified_itinerary": {
    "start_date": "2026-04-10",
    "end_date": "2026-04-12",
    "trip_days": 3,
    "nights": 2,
    "people_count": 2,
    "tags": ["미식", "로컬"],
    "title": "도쿄 로컬 여행",
    "summary": "로컬 미식을 중심으로 구성한 일정입니다.",
    "itinerary": []
  }
}
```

`SUCCESS`가 아닌 경우 `modified_itinerary`는 포함하지 않거나 `null`입니다.
내부 직렬화 과정에서 `modified_itinerary.planning_preference`는 콜백 payload에서 제거됩니다.

## 상태값

| 상태 | 의미 |
| --- | --- |
| `GENERAL_CHAT` | 로드맵 변경 없이 일반 답변 완료 |
| `SUCCESS` | 로드맵 수정 완료 |
| `ASK_CLARIFICATION` | 수정 대상이나 의도가 모호해 추가 확인 필요 |
| `REJECTED` | 정책상 처리할 수 없는 요청 |
| `FAILED` | 타임아웃 또는 내부 오류 |

## 예외와 실패 처리

| 상황 | 처리 |
| --- | --- |
| 대상 일자 또는 순서가 없음 | 오류 또는 반려 메시지 생성 |
| 하루 장소 수 10개 초과 | `REJECTED` |
| 하루 장소 수 1개 미만 | `REJECTED` |
| Google Places 검색 실패 | 장소 검색 실패 메시지 |
| 검색 결과 없음 | `ASK_CLARIFICATION`, 대체 검색어가 있으면 제안 |
| 일차 전체 삭제 요청 | `REJECTED` |
| 여행 날짜, 기간, 숙박 수 변경 요청 | `REJECTED` 또는 재구성 필요 안내 |
| LLM 응답 시간 초과 | `FAILED` 콜백, `LLM_TIMEOUT` |
| 내부 예외 | `FAILED` 콜백, `PIPELINE_ERROR` |

## 사용자 노출 기준

- 프론트엔드는 `diff_keys`를 사용해 변경된 장소 카드를 강조할 수 있습니다.
- 프론트엔드는 각 장소의 `place_category` 영문 코드를 한국어 라벨로 변환해 표시할 수 있습니다.
- `message`는 사용자에게 그대로 노출 가능한 단일 응답 문장입니다.
- `ASK_CLARIFICATION` 상태에서는 사용자의 추가 입력을 받아 같은 API로 다시 요청합니다.
- Undo/Redo는 현재 Python 워커가 직접 제공하지 않으며, 프론트엔드 또는 상위 서비스가 이전 로드맵 상태를 보관해 처리해야 합니다.

## 원본 문서 대비 현재 구현 차이

> [!NOTE]
> 원본 문서에는 영업시간 기반 반려, 토큰 제한 시 target day slicing, 일자 간 이동 가능성 등이 포함되어 있었습니다.
> 현재 구현은 Google Places 검색과 bbox 기반 필터링, LLM rerank, visit time policy를 중심으로 동작하며 영업시간 검증은 명시적으로 구현되어 있지 않습니다.
> 따라서 이 문서는 현재 코드에서 확인되는 동작만 기준으로 작성합니다.

## 코드 진입점과 검증

| 구분 | 위치 | 확인 내용 |
| --- | --- | --- |
| API 라우터 | `app/api/chat.py` | `/api/v1/chat` 요청 수락, 인증 의존성, 비동기 작업 시작 |
| 서비스 | `app/services/chat_service.py` | 채팅 그래프 실행, timeout 처리, callback payload 생성 |
| 그래프 정의 | `app/graph/chat/workflow.py` | 의도 분석 이후 분기와 노드 연결 |
| 그래프 노드 | `app/graph/chat/nodes/` | 의도 분석, 일반 답변, JSON 변경, 시간 제안, cascade, 응답 생성 |
| LLM/유틸 | `app/graph/chat/llm.py`, `app/graph/chat/utils.py` | 의도 분석 프롬프트, fallback, 응답 구성 보조 |
| 요청/응답 스키마 | `app/schemas/chat.py`, `app/schemas/course.py` | 채팅 요청, 로드맵 상태, 수정 응답 모델 |
| 장소 검색 | `app/services/google_places_service.py`, `app/services/places_service.py`, `app/services/place_rerank_service.py` | 교체/추가 장소 검색과 rerank 정책 |
| 테스트 | `tests/test_chat_schema.py`, `tests/test_timeout_policy.py` | 채팅 스키마 직렬화, timeout 정책 |

# 관련 문서

- [로드맵 채팅 수정 정책 확장 결정](../decisions/roadmap-chat-modification-policy.md)
- [모행 프로젝트 개요](../context/project-overview.md)
- [로드맵 채팅 API](../api/chat-api.md)
- [로드맵 채팅 수정 서버 간 통신 구조](../architecture/roadmap-chat-server-communication.md)

# TODO

- 영업시간 검증이 필요하면 Google Places 상세 응답과 visit_time 정책을 연결하는 별도 검증 단계를 설계합니다.
- 복합 수정 요청을 여러 operation으로 분해해 순차 적용할지 결정합니다.
