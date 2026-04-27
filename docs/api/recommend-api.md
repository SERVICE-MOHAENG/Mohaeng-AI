---
title: "여행지 추천 API"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [api, recommend, survey, callback]
ai_action: "editable"
---

# 요약

`POST /api/v1/recommend`는 NestJS가 Mohaeng-AI에 설문 기반 여행지 추천 작업을 위임하는 API입니다.
요청은 즉시 `202 ACCEPTED`로 수락되며, 실제 추천 결과는 `callback_url` 기반 NestJS 콜백으로 전달됩니다.

# 배경

추천 작업은 사용자의 설문 응답을 LLM에 전달해 후보 지역 중 정확히 5개를 선택하는 비동기 작업입니다.
Mohaeng-AI는 추천 결과를 직접 저장하지 않고 NestJS 콜백으로 전달합니다.

# 본문

## Endpoint

| 항목 | 내용 |
| --- | --- |
| Method | `POST` |
| Path | `/api/v1/recommend` |
| Status | `202 ACCEPTED` |
| 인증 | `x-service-secret` 헤더 |
| Request model | `RecommendRequest` |
| Response model | `RecommendAckResponse` |

## Request Headers

| 헤더 | 필수 | 설명 |
| --- | --- | --- |
| `x-service-secret` | Yes | NestJS와 Mohaeng-AI 사이의 서비스 인증 값 |
| `Content-Type` | Yes | `application/json` |

## Request Body

```json
{
  "job_id": "recommend-job-12345",
  "callback_url": "https://api.example.com",
  "weather": "OCEAN_BEACH",
  "travel_range": "MEDIUM_HAUL",
  "travel_style": "MODERN_TRENDY",
  "budget_level": "BALANCED",
  "food_personality": ["LOCAL_HIDDEN_GEM"],
  "main_interests": ["SHOPPING_TOUR", "DYNAMIC_ACTIVITY"]
}
```

## Request Fields

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | BullMQ 작업 ID |
| `callback_url` | URL | Yes | NestJS 콜백 베이스 URL |
| `weather` | enum 또는 null | No | 선호 날씨 |
| `travel_range` | enum 또는 null | No | 여행 거리 선호 |
| `travel_style` | enum 또는 null | No | 여행 스타일 |
| `budget_level` | enum 또는 null | No | 예산 선호 |
| `food_personality` | enum array 또는 null | No | 음식 성향 |
| `main_interests` | enum array 또는 null | No | 주요 관심사 |

## Enum Values

| 필드 | 값 |
| --- | --- |
| `weather` | `OCEAN_BEACH`, `SNOW_HOT_SPRING`, `CLEAN_CITY_BREEZE`, `INDOOR_LANDMARK` |
| `travel_range` | `SHORT_HAUL`, `MEDIUM_HAUL`, `LONG_HAUL` |
| `travel_style` | `MODERN_TRENDY`, `HISTORIC_RELAXED`, `PURE_NATURE` |
| `budget_level` | `COST_EFFECTIVE`, `BALANCED`, `PREMIUM_LUXURY` |
| `food_personality` | `LOCAL_HIDDEN_GEM`, `FINE_DINING`, `INSTAGRAMMABLE` |
| `main_interests` | `SHOPPING_TOUR`, `DYNAMIC_ACTIVITY`, `ART_AND_CULTURE` |

## Response

```json
{
  "job_id": "recommend-job-12345",
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

성공 콜백은 정확히 5개의 추천 지역을 포함합니다.

```json
{
  "status": "SUCCESS",
  "data": {
    "recommended_destinations": [
      { "region_name": "MALDIVES" },
      { "region_name": "HAWAII" },
      { "region_name": "ZANZIBAR" },
      { "region_name": "CANCUN" },
      { "region_name": "BALI" }
    ]
  }
}
```

실패 콜백은 다음 형태입니다.

```json
{
  "status": "FAILED",
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "Analysis took too long to complete."
  }
}
```

# 관련 문서

- [설문 기반 여행지 추천 기능](../specs/recommend-destinations.md)
- [여행지 추천 서버 간 통신 구조](../architecture/recommend-server-communication.md)
- [시장 문제와 타겟 사용자](../context/market-and-target-users.md)

# TODO

- 추천 결과에 추천 사유가 추가되면 callback schema를 함께 갱신합니다.
