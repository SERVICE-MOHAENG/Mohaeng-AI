---
title: "로드맵 생성 API"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [api, generate, roadmap, callback]
ai_action: "editable"
---

# 요약

`POST /api/v1/generate`는 NestJS가 Mohaeng-AI에 로드맵 생성 작업을 위임하는 API입니다.
요청은 즉시 `202 ACCEPTED`로 수락되며, 실제 생성 결과는 `callback_url` 기반 NestJS 콜백으로 전달됩니다.

# 배경

로드맵 생성은 LLM 호출과 Google Places 검색을 포함하는 장기 작업입니다.
클라이언트가 동기 대기하지 않도록 NestJS는 작업을 큐에 등록한 뒤 Mohaeng-AI를 호출하고, Mohaeng-AI는 비동기로 처리합니다.

# 본문

## Endpoint

| 항목 | 내용 |
| --- | --- |
| Method | `POST` |
| Path | `/api/v1/generate` |
| Status | `202 ACCEPTED` |
| 인증 | `x-service-secret` 헤더 |
| Request model | `GenerateRequest` |
| Response model | `GenerateAckResponse` |

## Request Headers

| 헤더 | 필수 | 설명 |
| --- | --- | --- |
| `x-service-secret` | Yes | NestJS와 Mohaeng-AI 사이의 서비스 인증 값 |
| `Content-Type` | Yes | `application/json` |

## Request Body

```json
{
  "job_id": "generate-job-12345",
  "callback_url": "https://api.example.com",
  "payload": {
    "start_date": "2026-02-07",
    "end_date": "2026-02-09",
    "regions": [
      {
        "region": "SEOUL",
        "start_date": "2026-02-07",
        "end_date": "2026-02-09"
      }
    ],
    "people_count": 2,
    "companion_type": ["FAMILY"],
    "travel_themes": ["UNIQUE_TRIP"],
    "pace_preference": "DENSE",
    "planning_preference": "PLANNED",
    "destination_preference": "TOURIST_SPOTS",
    "activity_preference": "ACTIVE",
    "priority_preference": "EFFICIENCY",
    "notes": "전시와 맛집 위주로 추천해 주세요."
  }
}
```

## Request Fields

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | NestJS가 발급한 작업 ID |
| `callback_url` | URL | Yes | 결과를 받을 NestJS 콜백 베이스 URL 또는 완성 URL |
| `payload` | object | Yes | 로드맵 생성 입력값 |
| `payload.start_date` | date | Yes | 여행 시작일 |
| `payload.end_date` | date | Yes | 여행 종료일 |
| `payload.regions` | array | Yes | 지역별 여행 기간, 1개 이상 8개 이하 |
| `payload.people_count` | integer | Yes | 총 인원 수, 1~20 |
| `payload.companion_type` | array | Yes | 동행자 유형, 1개 이상 |
| `payload.travel_themes` | array | Yes | 여행 테마, 1개 이상 |
| `payload.pace_preference` | enum | Yes | `DENSE`, `RELAXED` |
| `payload.planning_preference` | enum | Yes | `PLANNED`, `SPONTANEOUS` |
| `payload.destination_preference` | enum | Yes | `TOURIST_SPOTS`, `LOCAL_EXPERIENCE` |
| `payload.activity_preference` | enum | Yes | `ACTIVE`, `REST_FOCUSED` |
| `payload.priority_preference` | enum | Yes | `EFFICIENCY`, `EMOTIONAL` |
| `payload.notes` | string 또는 null | No | 추가 요청 사항 |

## Response

```json
{
  "job_id": "generate-job-12345",
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

## 입력 검증 규칙

- `end_date`는 `start_date`와 같거나 이후여야 합니다.
- 전체 여행 기간은 최대 8일이어야 합니다.
- `payload.regions`는 1개 이상 8개 이하이어야 합니다.
- 각 지역 구간의 `end_date`는 해당 `start_date`와 같거나 이후여야 합니다.
- 각 지역 구간은 전체 여행 기간 안에 포함되어야 합니다.
- 스켈레톤 생성 단계에서 지역 구간 사이 날짜 공백과 겹침을 검증합니다.
- 지역 구간을 정렬했을 때 전체 여행 기간을 빠짐없이 덮어야 합니다.

## Callback

성공 콜백은 `GenerateCallbackSuccess` 형식입니다.

```json
{
  "status": "SUCCESS",
  "data": {
    "start_date": "2026-02-07",
    "end_date": "2026-02-09",
    "trip_days": 3,
    "nights": 2,
    "people_count": 2,
    "tags": ["서울", "전시", "맛집"],
    "title": "서울 감성 여행",
    "summary": "전시와 미식을 중심으로 구성한 서울 일정입니다.",
    "itinerary": [
      {
        "day_number": 1,
        "daily_date": "2026-02-07",
        "places": [
          {
            "place_name": "국립현대미술관 서울",
            "place_id": "google-place-id",
            "address": "서울 종로구 삼청로 30",
            "latitude": 37.5787,
            "longitude": 126.9809,
            "place_url": "https://maps.google.com/?q=place_id:google-place-id",
            "place_category": "CULTURE",
            "description": "도심에서 전시를 즐길 수 있는 공간입니다.",
            "visit_sequence": 1,
            "visit_time": "09:00"
          }
        ]
      }
    ],
    "llm_commentary": "사용자 요청을 반영해 이동 부담이 적은 순서로 구성했습니다.",
    "next_action_suggestion": ["이 로드맵을 일정 밀도만 조정해서 다시 만들어줘."]
  }
}
```

`itinerary[].places[].place_category`는 Mohaeng 장소 대분류 코드입니다.
Google Places 원본 `primaryType`과 `types`는 내부 분류에만 사용하고 최종 콜백에는 포함하지 않습니다.
알 수 없는 유형은 `OTHER`로 전달합니다.
일자별 장소 순서는 FOOD 장소를 anchor로 고정한 내부 동선 최적화 결과이며, `visit_sequence`와 `visit_time`은 최종 순서 기준으로 재계산됩니다.
`planning_preference`가 `PLANNED`이면 `visit_time`은 `HH:MM`, `SPONTANEOUS`이면 `MORNING`/`LUNCH` 같은 section label 형식으로 전달됩니다.
anchor 여부나 최적화 점수 같은 내부 판단값은 콜백에 포함하지 않습니다.

실패 콜백은 `GenerateCallbackFailure` 형식입니다.

```json
{
  "status": "FAILED",
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "LLM 생성 시간이 초과되었습니다."
  }
}
```

## 구현 위치

| 구분 | 위치 |
| --- | --- |
| FastAPI 라우터 | `app/api/generate.py` |
| 요청/ACK 스키마 | `app/schemas/generate.py` |
| 로드맵 payload 스키마 | `app/schemas/course.py` |
| 생성 서비스 | `app/services/generate_service.py` |
| callback 전송 | `app/services/callback_delivery.py`, `app/services/callback_url.py` |

# 관련 문서

- [로드맵 생성 기능](../specs/roadmap-generation.md)
- [로드맵 생성 서버 간 통신 구조](../architecture/roadmap-generation-server-communication.md)
- [여행 일정 생성을 위한 AI 파이프라인 및 데이터 소스 선정](../decisions/roadmap-generation-ai-pipeline.md)

# TODO

- NestJS 콜백 수신 API의 최종 응답 코드 정책이 확정되면 콜백 섹션을 보강합니다.
