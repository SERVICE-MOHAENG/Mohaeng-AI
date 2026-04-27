---
title: "로드맵 채팅 API"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [api, chat, roadmap, modification, callback]
ai_action: "editable"
---

# 요약

`POST /api/v1/chat`은 NestJS가 Mohaeng-AI에 로드맵 대화 또는 수정 작업을 위임하는 API입니다.
요청은 즉시 `202 ACCEPTED`로 수락되며, 실제 결과는 `callback_url` 기반 NestJS 콜백으로 전달됩니다.

# 배경

채팅 요청은 일반 질문일 수도 있고, 기존 로드맵의 장소를 교체, 추가, 삭제, 이동하는 수정 요청일 수도 있습니다.
Mohaeng-AI는 최신 로드맵과 사용자 발화를 받아 의도를 분석하고, 필요한 경우 Google Places 검색과 visit time 재계산을 수행합니다.

# 본문

## Endpoint

| 항목 | 내용 |
| --- | --- |
| Method | `POST` |
| Path | `/api/v1/chat` |
| Status | `202 ACCEPTED` |
| 인증 | `x-service-secret` 헤더 |
| Request model | `ChatRequest` |
| Response model | `ChatAckResponse` |

## Request Headers

| 헤더 | 필수 | 설명 |
| --- | --- | --- |
| `x-service-secret` | Yes | NestJS와 Mohaeng-AI 사이의 서비스 인증 값 |
| `Content-Type` | Yes | `application/json` |

## Request Body

```json
{
  "job_id": "modify-job-12345",
  "callback_url": "https://api.example.com",
  "current_itinerary": {
    "start_date": "2026-02-11",
    "end_date": "2026-02-11",
    "trip_days": 1,
    "nights": 0,
    "people_count": 2,
    "tags": ["도심", "전시"],
    "title": "서울 당일치기 문화 코스",
    "summary": "도심 전시와 식사를 균형 있게 즐기는 일정입니다.",
    "planning_preference": "PLANNED",
    "itinerary": []
  },
  "companion_type": ["FAMILY"],
  "travel_themes": ["UNIQUE_TRIP"],
  "pace_preference": "DENSE",
  "planning_preference": "PLANNED",
  "destination_preference": "TOURIST_SPOTS",
  "activity_preference": "ACTIVE",
  "priority_preference": "EFFICIENCY",
  "user_query": "1일차 1번째 장소를 미술관으로 바꿔줘",
  "session_history": [
    {
      "role": "user",
      "content": "서울 당일치기 일정 만들어줘"
    }
  ]
}
```

## Request Fields

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | NestJS BullMQ 작업 ID |
| `callback_url` | URL | Yes | 결과를 받을 NestJS 콜백 URL |
| `current_itinerary` | object | Yes | 현재 세션의 전체 로드맵 |
| `companion_type` | array | Yes | 동행자 유형, 1개 이상 |
| `travel_themes` | array | Yes | 여행 테마, 1개 이상 |
| `pace_preference` | enum | Yes | `DENSE`, `RELAXED` |
| `planning_preference` | enum | Yes | `PLANNED`, `SPONTANEOUS` |
| `destination_preference` | enum | Yes | `TOURIST_SPOTS`, `LOCAL_EXPERIENCE` |
| `activity_preference` | enum | Yes | `ACTIVE`, `REST_FOCUSED` |
| `priority_preference` | enum | Yes | `EFFICIENCY`, `EMOTIONAL` |
| `user_query` | string | Yes | 사용자 발화, 최소 1자 |
| `session_history` | array | No | 최근 대화 맥락 |

## Response

```json
{
  "job_id": "modify-job-12345",
  "status": "ACCEPTED"
}
```

## Error Responses

| Status | 상황 |
| --- | --- |
| `401` | `x-service-secret` 누락 또는 불일치 |
| `422` | 요청 body 스키마 검증 실패 |
| `500` | 서버 설정 누락 또는 예상하지 못한 오류 |
| `504` | 요청 단위 타임아웃 |

## Callback

성공 콜백은 수정된 로드맵을 포함합니다.

```json
{
  "status": "SUCCESS",
  "message": "요청하신 대로 1일차 1번째 장소를 변경했습니다.",
  "diff_keys": ["day1_place1"],
  "modified_itinerary": {
    "start_date": "2026-02-11",
    "end_date": "2026-02-11",
    "trip_days": 1,
    "nights": 0,
    "people_count": 2,
    "tags": ["도심", "전시"],
    "title": "서울 당일치기 문화 코스",
    "summary": "도심 전시와 식사를 균형 있게 즐기는 일정입니다.",
    "itinerary": []
  }
}
```

일반 대화, 추가 확인, 반려 콜백은 `modified_itinerary`가 `null`입니다.

```json
{
  "status": "ASK_CLARIFICATION",
  "message": "삭제할 일차와 장소 순서를 함께 알려주세요. 예: '1일차 2번째 장소 삭제해줘'",
  "diff_keys": [],
  "modified_itinerary": null
}
```

실패 콜백은 다음 형태입니다.

```json
{
  "status": "FAILED",
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "LLM 응답 시간이 초과되었습니다."
  }
}
```

## Status Values

| 값 | 의미 |
| --- | --- |
| `GENERAL_CHAT` | 로드맵 변경 없는 일반 답변 |
| `SUCCESS` | 로드맵 수정 성공 |
| `ASK_CLARIFICATION` | 추가 확인 필요 |
| `REJECTED` | 정책상 처리 불가 |
| `FAILED` | 타임아웃 또는 내부 오류 |

# 관련 문서

- [로드맵 채팅 수정 기능](../specs/roadmap-chat-modification.md)
- [로드맵 채팅 수정 서버 간 통신 구조](../architecture/roadmap-chat-server-communication.md)

# TODO

- 프론트엔드가 사용하는 `diff_keys` 렌더링 규칙이 확정되면 예시를 보강합니다.
