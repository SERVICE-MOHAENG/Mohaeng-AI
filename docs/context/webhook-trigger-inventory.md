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

# 유지/제거 기준

판단 기준은 다음 세 가지입니다.

| 기준 | 유지 쪽 판단 | 제거 쪽 판단 |
| --- | --- | --- |
| 운영 장애 감지 | 서비스 중단, 요청 폭주, 콜백 실패처럼 즉시 대응이 필요한 이벤트 | 상세 단계별 성공 알림처럼 장애와 직접 연결되지 않는 이벤트 |
| 중복성 | 하나의 실패를 유일하게 나타내는 이벤트 | 같은 의미를 여러 단계에서 반복해서 보내는 이벤트 |
| 노이즈 | 알림 빈도가 낮고 실제 대응 가치가 높음 | 정상 흐름마다 반복되어 관측성을 흐리는 이벤트 |

즉, 남길 웹훅은 “서비스가 정상적으로 살아 있는지” 또는 “실패해서 운영자가 알아야 하는지”를 알려주는 것만입니다.
제거할 웹훅은 “각 단계가 잘 끝났다는 사실”을 지나치게 세분화해서 알리는 것들입니다.

# 남길 웹훅

## 1. `server_start`

### 이유
- 서비스가 실제로 기동했는지 확인하는 가장 기본적인 운영 신호입니다.
- 배포 직후 헬스체크가 통과했는지, 프로세스가 정상 시작됐는지 빠르게 확인할 수 있습니다.

### 운영 가치
- 장애 대응 시 “서버가 떠 있는가”를 즉시 판단할 수 있습니다.
- 배포 실패나 시작 직후 크래시를 빠르게 감지할 수 있습니다.

## 2. `server_shutdown`

### 이유
- 의도하지 않은 종료, 배포 교체, 프로세스 재시작 여부를 추적하는 데 필요합니다.
- 서버 생명주기상 종료는 시작만큼이나 중요한 운영 이벤트입니다.

### 운영 가치
- 예기치 않은 중단과 정상 종료를 구분하는 단서가 됩니다.
- 운영 로그와 함께 보면 배포 또는 프로세스 재기동 시점을 맞추기 쉽습니다.

## 3. `http_500`

### 이유
- 처리되지 않은 예외는 사용자 영향이 직접적이고, 반드시 알아야 하는 장애 신호입니다.
- 500은 요청 단위 타임아웃보다 더 강한 경고입니다.

### 운영 가치
- 코드 경로에서 예상하지 못한 예외가 어디서 터졌는지 바로 알 수 있습니다.
- 사용자가 실패를 겪는 순간에 대응할 수 있습니다.

## 4. `request_timeout`

### 이유
- 요청 레벨에서 응답이 늦어지는 것은 사용자 체감 품질 저하로 직결됩니다.
- 처리 지연이 누적되기 전에 조기 경보를 주는 용도로 적합합니다.

### 운영 가치
- 특정 API가 느려졌는지 확인하는 지표 역할을 합니다.
- `500`보다 선행하는 성능 이상 신호로 쓸 수 있습니다.

## 5. `callback_delivery_failed`

### 이유
- 이 서비스는 비동기 작업 결과를 NestJS 콜백으로 전달하므로, 콜백 실패는 실제 사용자 결과 누락으로 이어질 수 있습니다.
- 재시도 후에도 실패한 경우는 운영자가 알아야 합니다.

### 운영 가치
- 작업은 끝났는데 결과 전달이 실패한 상태를 추적할 수 있습니다.
- 백엔드/워커 자체 문제와 외부 콜백 수신 실패를 분리해서 볼 수 있습니다.

## 6. `pipeline_timeout`

### 이유
- 채팅, 생성, 추천과 같은 작업이 제한 시간을 초과하면 결과를 정상 전달하지 못할 수 있습니다.
- timeout은 기능 장애와 사용자 대기 증가를 동시에 의미합니다.

### 운영 가치
- 어떤 job 타입이 자주 느려지는지 판단할 수 있습니다.
- 성능 회귀나 외부 API 병목을 파악하는 데 필요합니다.

# 제거해야 할 웹훅

## 1. `llm_call_success`

### 제거 이유
- 정상 성공은 너무 자주 발생합니다.
- 모든 LLM 호출마다 알림이 가면 운영자가 중요한 실패를 놓치게 됩니다.

### 왜 없어도 되는가
- 성공 자체는 job 완료 로그, 내부 job log, 메트릭으로 충분히 확인 가능합니다.
- 운영 관점에서 “정상 호출됨”보다 “실패함”이 더 중요합니다.

## 2. `llm_call_failed`

### 제거 이유
- 첫 실패가 곧 최종 실패는 아닙니다.
- fallback 구조가 있기 때문에 1차 실패만 알리면 오탐 알림이 많아집니다.

### 왜 없어도 되는가
- 최종 실패는 `llm_fallback_failed` 또는 상위 파이프라인 실패로 충분히 대표됩니다.

## 3. `llm_call_retry`

### 제거 이유
- 재시도 진입 자체는 운영 장애라기보다 내부 복구 동작입니다.
- retry는 노이즈가 많고, 반복 호출이 잦은 LLM 경로에서는 알림 폭주를 만듭니다.

### 왜 없어도 되는가
- 실제로 복구됐는지 여부는 최종 성공/실패로 충분히 판단할 수 있습니다.

## 4. `llm_fallback_success`

### 제거 이유
- fallback 성공은 시스템이 스스로 복구했다는 의미이지만, 빈도가 높아지면 노이즈가 됩니다.
- 운영자가 매번 알아야 할 수준의 이벤트는 아닙니다.

### 왜 없어도 되는가
- fallback이 자주 발생한다면 메트릭/로그로 추세를 보는 편이 더 낫습니다.
- 알림은 최종 실패만 남기는 쪽이 관측성이 좋습니다.

## 5. `chat_started`

### 제거 이유
- 요청 수만큼 발생하는 시작 알림은 과도합니다.
- 시작 자체는 장애가 아니라 정상 흐름입니다.

### 왜 없어도 되는가
- job log와 내부 상태로 충분히 추적 가능합니다.
- 완료나 timeout, 실패가 더 유의미한 운영 신호입니다.

## 6. `chat_completed`

### 제거 이유
- 성공/실패 여부를 job 완료 이벤트로 이미 간접 확인할 수 있습니다.
- 채팅은 사용자 요청량이 많은 경로라 알림 빈도가 높아집니다.

### 왜 없어도 되는가
- 종료 사실보다는 실패와 timeout이 더 중요합니다.
- 정상 완료는 메트릭과 로그로 대체하는 것이 적합합니다.

## 7. `generate_started`

### 제거 이유
- 생성 작업은 정상 처리 시작이 흔한 이벤트이며, 알림 가치가 낮습니다.
- 운영자가 매 요청 시작을 받을 필요는 없습니다.

### 왜 없어도 되는가
- timeout, 실패, 최종 완료가 더 중요한 경계 이벤트입니다.

## 8. `generate_completed`

### 제거 이유
- 생성 성공 알림은 빈도가 높고, 운영상 필수 정보는 아닙니다.
- job 단위 완료 알림은 다른 로그/메트릭과 역할이 겹칩니다.

### 왜 없어도 되는가
- timeout과 실패만 남겨도 운영 대응에는 충분합니다.

## 9. `chat_intent_routed`

### 제거 이유
- 일반 대화로 분류됐다는 사실은 운영 장애가 아닙니다.
- 가장 빈도가 높은 분기 중 하나라 알림 노이즈가 큽니다.

### 왜 없어도 되는가
- 라우팅 성공 여부는 내부 로그로 충분히 확인 가능합니다.

## 10. `chat_intent_rejected`

### 제거 이유
- 의도적으로 거부한 요청은 사용자 정책상 정상 동작입니다.
- 다만 현재 규칙이 자주 맞물리면 알림이 과도해질 수 있습니다.

### 왜 없어도 되는가
- 거부 사유는 API 응답과 로그에 남기면 충분합니다.

## 11. `chat_intent_clarification`

### 제거 이유
- 추가 확인 요청은 사용자 상호작용의 일부이며, 운영 장애가 아닙니다.
- 대화형 서비스 특성상 빈번할 수 있습니다.

### 왜 없어도 되는가
- 사용자에게 실제로 반환된 확인 질문이 더 중요합니다.

## 12. `chat_intent_parsed`

### 제거 이유
- 내부 의도 파싱 성공은 기능 정상 흐름입니다.
- 단계별 성공 알림은 세밀하지만 운영 가치가 낮습니다.

### 왜 없어도 되는가
- 수정 파이프라인이 성공했다는 사실은 최종 응답이나 callback으로 충분히 확인됩니다.

## 13. `chat_intent_failed`

### 제거 이유
- 이 이벤트는 실패를 나타내지만, 상위 파이프라인 실패와 중복될 수 있습니다.
- 의도 분석 실패는 결국 채팅 실패 흐름으로 수렴합니다.

### 왜 없어도 되는가
- 최종 실패 알림만 유지하고, 상세 원인은 서버 로그로 추적하는 편이 더 단순합니다.

## 14. `chat_mutate_completed`

### 제거 이유
- 실제 수정 반영은 내부 처리 단계이며, 매번 알림할 수준의 운영 신호는 아닙니다.
- 수정 요청이 많은 서비스에서는 알림 폭주가 빠르게 발생합니다.

### 왜 없어도 되는가
- 변경 결과는 callback payload와 job log로 확인 가능합니다.

## 15. `chat_response_completed`

### 제거 이유
- 자연어 응답 생성 완료는 정상 완료에 해당합니다.
- 응답 단계는 매우 자주 발생하므로 웹훅으로 보기에는 과합니다.

### 왜 없어도 되는가
- 최종 사용자 응답은 API 응답 자체와 로그로 확인 가능합니다.

## 16. `roadmap_skeleton_completed`

### 제거 이유
- 생성 파이프라인의 중간 정상 단계입니다.
- 스켈레톤 완료를 매번 알리면 단계별 성공 알림이 너무 많아집니다.

### 왜 없어도 되는가
- 최종 성공/실패와 timeout만 남기면 충분합니다.

## 17. `roadmap_places_completed`

### 제거 이유
- 장소 수집은 중간 단계이며, 성공이 반복되는 정상 흐름입니다.
- 운영상 중요한 장애는 장소 수집 자체보다 최종 실패나 timeout입니다.

### 왜 없어도 되는가
- 단계 성공 알림보다 실패와 성능 문제 감지가 더 중요합니다.

## 18. `roadmap_finalize_desc`

### 제거 이유
- 최종 합성 중 세부 단계 성공 알림입니다.
- description 보강은 내부 구현 디테일이며 운영 신호로는 과합니다.

### 왜 없어도 되는가
- 최종 결과 생성 성공 여부로 충분합니다.

## 19. `roadmap_finalize_time`

### 제거 이유
- visit time 보정 역시 세부 구현 단계입니다.
- 최종 로드맵 성공 여부와 중복됩니다.

### 왜 없어도 되는가
- 세부 보정 성공은 로그나 디버그 수준으로 충분합니다.

## 20. `roadmap_finalize_completed`

### 제거 이유
- 이 이벤트는 최종 성공 알림이지만, 생성 서비스의 `generate_completed`와 의미가 겹칩니다.
- 동일 파이프라인 안에서 완료 알림이 여러 번 나가면 관측성이 떨어집니다.

### 왜 없어도 되는가
- 상위 레벨의 job 완료 1건만 남기는 편이 운영상 더 선명합니다.

## 21. `roadmap_finalize_failed`

### 제거 이유
- 실패 자체는 중요하지만, 이 이벤트는 상위 파이프라인 실패와 중복될 수 있습니다.
- 특히 최종 합성 실패는 `generate_completed` 실패나 job log로도 충분히 드러납니다.

### 왜 없어도 되는가
- 최종 실패는 상위 job 실패와 로그로 대표하고, 세부 원인은 서버 로그로 보는 편이 낫습니다.

# 권장 정리 방향

현 코드 기준으로는 다음처럼 줄이는 것이 가장 합리적입니다.

| 유지 | 제거 |
| --- | --- |
| `server_start` | `llm_call_success` |
| `server_shutdown` | `llm_call_failed` |
| `http_500` | `llm_call_retry` |
| `request_timeout` | `llm_fallback_success` |
| `callback_delivery_failed` | `chat_started` |
| `pipeline_timeout` | `chat_completed` |
|  | `generate_started` |
|  | `generate_completed` |
|  | `chat_intent_*` 전체 |
|  | `chat_mutate_completed` |
|  | `chat_response_completed` |
|  | `roadmap_skeleton_completed` |
|  | `roadmap_places_completed` |
|  | `roadmap_finalize_desc` |
|  | `roadmap_finalize_time` |
|  | `roadmap_finalize_completed` |
|  | `roadmap_finalize_failed` |

이 기준의 핵심은 “운영자가 실제로 지금 알아야 하는 것만 알린다”입니다.
즉, 정상 단계의 성공 알림은 최대한 제거하고, 장애·timeout·전달 실패처럼 복구/대응이 필요한 이벤트만 남기는 것이 목표입니다.

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
