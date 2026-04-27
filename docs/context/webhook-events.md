---
title: "Mohaeng-AI 웹훅 이벤트 목록"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [context, webhook, discord, observability, events]
ai_action: "reference-only"
---

# 요약

이 문서는 Mohaeng-AI 서버가 실제로 보내는 Discord 웹훅 이벤트를 정리합니다.
목적은 운영자가 웹훅 한 건만 보더라도 어떤 작업에서 어떤 상태가 발생했는지 빠르게 파악할 수 있게 하는 것입니다.

# 공통 규칙

- 모든 웹훅은 Discord로 전송됩니다.
- `job_id`는 영어 키로 유지합니다.
- 화면에 보이는 제목과 라벨은 한국어 우선으로 작성합니다.
- 성공 이벤트보다 실패 이벤트를 더 자세히 남깁니다.
- 내부 구현 식별자 `event_type`은 유지하지만, 사용자에게 보이는 제목은 한국어를 우선합니다.

# 현재 유지 중인 웹훅

## 서버 운영

### `server_start`

서버가 기동되었음을 알립니다.
환경명, Python 버전, 호스트명이 함께 전송됩니다.

### `server_shutdown`

서버가 종료되었음을 알립니다.
호스트명이 함께 전송됩니다.

### `http_500`

전역 예외 처리기까지 도달한 처리되지 않은 HTTP 500 오류를 알립니다.
요청 메서드, 경로, 오류 메시지를 포함합니다.

### `request_timeout`

HTTP 요청 단위 타임아웃을 알립니다.
요청 메서드, 경로, 경과 시간이 포함됩니다.

### `pipeline_timeout`

채팅, 생성, 추천 같은 비동기 작업이 제한 시간을 넘었음을 알립니다.
작업 유형과 경과 시간이 포함됩니다.

### `callback_delivery_failed`

콜백 재시도가 모두 실패했음을 알립니다.
콜백 유형, 대상 URL, 오류 메시지가 포함됩니다.

## 채팅 수정

### `chat_started`

로드맵 채팅 수정 요청이 접수되었음을 알립니다.
사용자 발화 원문, 현재 로드맵, 요청 조건, 대화 이력이 포함됩니다.

### `chat_completed`

채팅 수정 작업이 실패했을 때만 전송합니다.
사용자 발화, 현재 로드맵, 요청 조건, 대화 이력, 오류 상세가 포함됩니다.

### `chat_intent_rejected`

정책상 허용되지 않는 수정 의도를 거부했음을 알립니다.
예: 일차 삭제, 일차 자체 변경.

### `chat_intent_failed`

수정 의도 분석 단계가 실패했음을 알립니다.
오류 유형과 판단 맥락이 포함됩니다.

## 로드맵 생성

### `generate_started`

로드맵 생성 요청이 접수되었음을 알립니다.
NestJS에서 받은 생성 요청 JSON 전체가 포함됩니다.

### `generate_completed`

로드맵 생성 작업이 실패했을 때만 전송합니다.
생성 요청 JSON, 오류 상세, 처리 단계, 경과 시간이 포함됩니다.

## 여행지 추천

### `recommend_request_received`

여행지 추천 요청이 접수되었음을 알립니다.
추천 요청 JSON 전체가 포함됩니다.

### `recommend_completed`

여행지 추천 작업이 실패했을 때만 전송합니다.
추천 요청 JSON, 오류 상세, 처리 단계, 경과 시간이 포함됩니다.

## LLM 라우팅

### `llm_call_failed`

주 모델의 LLM 호출이 실패했음을 알립니다.
실패한 단계, 선택된 모델, 오류 유형이 포함됩니다.

### `llm_fallback_failed`

주 모델과 fallback 모델 모두 실패했음을 알립니다.
실패한 단계, 최종 선택 모델, 오류 유형이 포함됩니다.

## 로드맵 합성

### `roadmap_finalize_failed`

로드맵 최종 합성 단계가 실패했음을 알립니다.
오류 유형과 최종 합성 단계의 맥락이 포함됩니다.

# 제외한 웹훅

- LLM 성공 알림
- LLM 재시도 성공 알림
- 단계별 성공 알림
- 로드맵 스켈레톤/장소 수집/최종 합성의 성공 알림
- 채팅 의도 파싱 성공 알림

이런 이벤트는 정상 경로에서 너무 자주 발생해 운영 알림 노이즈를 만들 수 있으므로 제외합니다.

# 관련 코드

- `app/services/webhook_notification.py`
- `app/services/chat_service.py`
- `app/services/generate_service.py`
- `app/services/recommend_service.py`
- `app/core/llm_router.py`
- `app/services/callback_delivery.py`

