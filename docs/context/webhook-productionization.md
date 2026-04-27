---
title: "웹훅 프로덕션화 기준"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [context, webhook, discord, observability, production]
ai_action: "reference-only"
---

# 요약

Mohaeng-AI의 Discord 웹훅은 운영 관측성에 필요한 최소 집합만 남기고 정리합니다.
이 문서는 현재 코드 기준으로 무엇을 남기고, 무엇을 제거할지에 대한 간단한 기준 문서입니다.

# 유지할 웹훅

## 인프라/운영 신호

남깁니다.
이 범주는 서비스 상태와 즉시 대응이 필요한 장애를 알려주는 최소 집합입니다.

### `server_start`

서비스가 정상 기동했는지 확인하는 기본 신호입니다.

### `server_shutdown`

의도된 종료인지 비정상 종료인지 추적하는 데 필요합니다.

### `http_500`

처리되지 않은 예외를 즉시 확인해야 할 때 필요합니다.

### `request_timeout`

요청 지연과 성능 회귀를 빠르게 잡기 위해 남깁니다.

### `pipeline_timeout`

채팅, 생성, 추천 같은 작업이 제한 시간을 넘었는지 알려주는 신호입니다.

### `callback_delivery_failed`

비동기 작업 결과가 실제 서버로 전달되지 못한 경우를 확인하는 마지막 신호입니다.

### `chat_started`

채팅 요청을 실제로 받았는지 확인하는 접수 신호입니다.

### `generate_started`

로드맵 생성 요청을 실제로 받았는지 확인하는 접수 신호입니다.

### `recommend_request_received`

여행지 추천 요청을 실제로 받았는지 확인하는 접수 신호입니다.
현재 코드에는 별도 웹훅이 없지만, 프로덕션화 기준상 유지해야 하는 운영 신호입니다.

## `chat_intent_rejected`

남깁니다.
이 이벤트는 단순한 거부 알림이 아니라, 사용자가 LLM에게 어떤 종류의 요청을 하는지 관측하는 신호입니다.
특히 삭제, 일차 변경, 거부된 수정 요청은 실제 사용자 의도와 정책 충돌을 보여주므로 운영상 유의미합니다.

## 파이프라인 실패 이벤트

남깁니다.
채팅, 생성, 추천, LLM 라우팅, 최종 합성에서 실패가 발생하면 웹훅으로 상세 내용을 보내야 합니다.
여기에는 job 유형, stage, status, retry 여부, fallback 여부, 에러 타입, 에러 메시지, elapsed time, 핵심 컨텍스트가 포함되어야 합니다.

이 범주의 목표는 “실패가 났다”가 아니라 “왜 실패했는지 바로 볼 수 있다”입니다.

### 유지 대상 예시

- `llm_call_failed`
- `llm_fallback_failed`
- `chat_completed` 실패
- `generate_completed` 실패
- `roadmap_finalize_failed`

# 제거할 웹훅

- LLM 성공/재시도/fallback 성공 알림
- 채팅/생성의 시작·완료 성공 알림
- 스켈레톤/장소 수집/최종 합성 같은 단계별 성공 알림
- 의도 파싱 성공 알림

위 항목들은 정상 흐름에서 너무 자주 발생해 운영 알림 노이즈를 만들기 쉽습니다.

# 정리 방향

- 성공 알림은 줄입니다.
- 실패 알림은 자세하게 남깁니다.
- 사용자의 요청 의도를 드러내는 `chat_intent_rejected`는 유지합니다.

# 관련 파일

- `app/services/webhook_notification.py`
- `app/core/llm_router.py`
- `app/services/chat_service.py`
- `app/services/generate_service.py`
- `app/services/recommend_service.py`
- `app/services/callback_delivery.py`
- `app/graph/chat/nodes/analyze_intent.py`
