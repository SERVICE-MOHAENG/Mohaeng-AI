---
title: "웹훅 트리거 전수조사"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [context, webhook, discord, observability, inventory]
ai_action: "reference-only"
---

# 요약

이 문서는 Mohaeng-AI 레포에서 실제로 Discord 웹훅을 발송하는 모든 트리거를 전수조사한 결과를 정리합니다.
목적은 웹훅을 줄이기 위한 기준 문서를 만드는 것이며, 지금 시점의 코드 기준으로 어떤 이벤트가 어디에서 발송되는지 빠르게 확인할 수 있게 하는 데 있습니다.

# 범위

조사 기준은 `app/` 하위의 실제 호출 지점입니다.
`__pycache__/`와 같은 생성물은 제외하고, 코드에서 `notify_*` 또는 `schedule_webhook()`을 통해 웹훅이 예약되거나 전송되는 지점만 포함했습니다.

중심 서비스는 `app/services/webhook_notification.py`이며, 실제 발송은 이 파일의 `notify_pipeline_event()`를 통해 Discord webhook URL로 나갑니다.

# 전수조사 결과

## 1. 웹훅 발송 구조

| 계층 | 역할 | 대표 파일 |
| --- | --- | --- |
| 공통 발송기 | Discord embed payload 구성 및 실제 HTTP 전송 | `app/services/webhook_notification.py` |
| 비동기 예약기 | 현재 이벤트 루프 또는 별도 스레드에서 fire-and-forget 예약 | `app/services/webhook_notification.py` |
| 앱 생명주기/HTTP 미들웨어 | 서버 시작/종료, request timeout, 500 에러 감지 | `app/main.py` |
| LLM 라우터 | LLM 호출 성공/실패/재시도/대체 모델 결과 알림 | `app/core/llm_router.py` |
| 채팅 파이프라인 | 채팅 시작/종료, 의도 분석, 수정 적용, 응답 완료 | `app/services/chat_service.py`, `app/graph/chat/nodes/*` |
| 생성 파이프라인 | 생성 시작/종료, 스켈레톤/장소/최종합성 완료, 실패 알림 | `app/services/generate_service.py`, `app/graph/roadmap/nodes/*` |
| 추천 파이프라인 | 추천 타임아웃 알림 | `app/services/recommend_service.py` |
| 콜백 전송 | 콜백 최종 실패 알림 | `app/services/callback_delivery.py` |

## 2. 공통 발송기 이벤트

`app/services/webhook_notification.py`에서 정의하는 표준 이벤트입니다.
이벤트 이름 자체가 Discord payload의 `event_type`으로 들어갑니다.

| `event_type` | 심각도 | stage | 발생 조건 | 호출 위치 |
| --- | --- | --- | --- | --- |
| `server_start` | `success` | `server` | FastAPI lifespan 시작 시 | `app/services/webhook_notification.py` |
| `server_shutdown` | `error` | `server` | FastAPI lifespan 종료 시 | `app/services/webhook_notification.py` |
| `http_500` | `error` | `http` | 전역 예외 처리기에 처리되지 않은 예외가 도달했을 때 | `app/main.py` |
| `request_timeout` | `warning` | `http` | 요청 middleware에서 `asyncio.wait_for()`가 timeout 되었을 때 | `app/main.py` |
| `pipeline_timeout` | `warning` | `job_type` | job 단위 timeout이 발생했을 때 | `app/services/webhook_notification.py`가 공통 포맷 생성 |
| `callback_delivery_failed` | `error` | `callback_type` | 콜백 재시도 후에도 전송 실패했을 때 | `app/services/callback_delivery.py` |

## 3. LLM 라우터 이벤트

`app/core/llm_router.py`는 `Stage`별 LLM 호출을 감싸면서 호출 성공/실패/재시도/대체 모델 성공/실패를 모두 웹훅으로 보냅니다.
같은 `event_type`이라도 동기 `invoke()`와 비동기 `ainvoke()`에서 각각 동일한 트리거가 발생합니다.

| `event_type` | 심각도 | 상태 | 발생 조건 | 비고 |
| --- | --- | --- | --- | --- |
| `llm_call_success` | `success` | `SUCCESS` | 1차 LLM 호출이 성공했을 때 | sync/async 모두 존재 |
| `llm_call_failed` | `error` | `FAILED` | fallback 대상이 아니거나 fallback 없이 실패했을 때 | sync/async 모두 존재 |
| `llm_call_retry` | `warning` | `RETRYING` | 1차 LLM 호출 실패 후 fallback 재시도에 들어갈 때 | sync/async 모두 존재 |
| `llm_fallback_success` | `warning` | `SUCCESS` | fallback 모델 호출이 성공했을 때 | sync/async 모두 존재 |
| `llm_fallback_failed` | `error` | `FAILED` | fallback 모델 호출까지 실패했을 때 | sync/async 모두 존재 |

## 4. 채팅 파이프라인 이벤트

### `app/services/chat_service.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `chat_started` | `info` | `STARTED` | 채팅 요청 처리 시작 직후 |
| `chat_completed` | `success` 또는 `error` | 요청 결과 상태 | 채팅 파이프라인 종료 후 |

### `app/graph/chat/nodes/analyze_intent.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `chat_intent_routed` | `info` | `GENERAL_CHAT` | 일반 대화로 분류되었을 때 |
| `chat_intent_rejected` | `warning` | `REJECTED` | 일차 삭제 요청 또는 일차 변경 요청이 거부되었을 때 |
| `chat_intent_clarification` | `warning` | `ASK_CLARIFICATION` | 삭제 대상이 모호하거나 추가 확인이 필요할 때 |
| `chat_intent_parsed` | `info` | `MODIFICATION` | 수정 의도 초안 파싱에 성공했을 때 |
| `chat_intent_failed` | `error` | `FAILED` | 수정 의도 파싱 자체가 실패했을 때 |

### `app/graph/chat/nodes/mutate.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `chat_mutate_completed` | `success` | 현재 상태값 | 수정 연산이 실제 일정에 반영되었을 때 |

### `app/graph/chat/nodes/respond.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `chat_response_completed` | `success` 또는 `warning` | 최종 상태값 | 자연어 응답 생성이 끝났을 때 |

## 5. 로드맵 생성 파이프라인 이벤트

### `app/services/generate_service.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `generate_started` | `info` | `STARTED` | 생성 요청 처리 시작 직후 |
| `generate_completed` | `success` 또는 `error` | 요청 결과 상태 | 생성 파이프라인 종료 후 |

### `app/graph/roadmap/nodes/skeleton.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `roadmap_skeleton_completed` | `success` | `SUCCESS` | 스켈레톤 검증과 보정이 끝났을 때 |

### `app/graph/roadmap/nodes/places.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `roadmap_places_completed` | `success` | `SUCCESS` | 슬롯별 장소 수집과 rerank가 끝났을 때 |

### `app/graph/roadmap/nodes/finalize.py`

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `roadmap_finalize_desc` | `success` | `SUCCESS` | 장소 description 보강이 끝났을 때 |
| `roadmap_finalize_time` | `success` | `SUCCESS` | visit time 보정이 끝났을 때 |
| `roadmap_finalize_completed` | `success` | `SUCCESS` | 최종 로드맵 합성이 끝났을 때 |
| `roadmap_finalize_failed` | `error` | `FAILED` | 최종 합성 단계에서 예외가 발생했을 때 |

## 6. 추천 파이프라인 이벤트

`app/services/recommend_service.py`는 현재 성공 이벤트를 보내지 않고, timeout 시에만 웹훅을 보냅니다.

| `event_type` | 심각도 | 상태 | 발생 조건 |
| --- | --- | --- | --- |
| `pipeline_timeout` | `warning` | `TIMEOUT` | 추천 작업이 제한 시간을 초과했을 때 |

# 현재 코드 기준 요약

현재 코드에서 관측되는 웹훅은 크게 4가지 성격으로 나뉩니다.

| 분류 | 성격 | 예시 |
| --- | --- | --- |
| 인프라/장애 | 서버 시작/종료, 500, request timeout | `server_start`, `http_500` |
| 파이프라인 운영 | job 시작/종료, timeout, callback 실패 | `chat_started`, `pipeline_timeout`, `callback_delivery_failed` |
| LLM 관측성 | 호출 성공, 실패, retry, fallback | `llm_call_success`, `llm_fallback_failed` |
| 단계별 세부 알림 | 채팅 의도 분석, 스켈레톤, 장소 수집, 최종 합성 | `chat_intent_parsed`, `roadmap_finalize_completed` |

이 문서는 제거 대상을 판단하기 위한 기준 문서이며, 실제 최소화 작업에서는 위 세부 단계 알림을 우선 정리 대상으로 볼 수 있습니다.

# 관련 파일

- `app/services/webhook_notification.py`
- `app/main.py`
- `app/core/llm_router.py`
- `app/services/chat_service.py`
- `app/services/generate_service.py`
- `app/services/recommend_service.py`
- `app/services/callback_delivery.py`
- `app/graph/chat/nodes/analyze_intent.py`
- `app/graph/chat/nodes/mutate.py`
- `app/graph/chat/nodes/respond.py`
- `app/graph/roadmap/nodes/skeleton.py`
- `app/graph/roadmap/nodes/places.py`
- `app/graph/roadmap/nodes/finalize.py`
