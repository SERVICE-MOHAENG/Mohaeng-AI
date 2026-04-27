---
title: "설문 기반 여행지 추천 기능"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [specs, recommendation, survey, llm, callback]
ai_action: "editable"
---

# 요약

설문 기반 여행지 추천 기능은 사용자의 여행 선호 입력을 받아 추천 지역 5개를 비동기로 생성합니다.
현재 구현은 pgvector나 임베딩 검색을 사용하지 않고, `Region` Enum 전체를 후보군으로 두고 LLM이 설문 의미에 맞는 지역을 선택하는 방식입니다.
요청 API는 `/api/v1/recommend`이며, 즉시 `ACCEPTED` 응답을 반환한 뒤 NestJS 콜백 URL로 성공 또는 실패 결과를 전달합니다.

# 배경

회원가입 또는 초기 온보딩 단계에서는 사용자의 취향을 빠르게 파악하고, 바로 선택 가능한 여행지 후보를 제시해야 합니다.
추천 결과는 최종 예약이나 일정 생성이 아니라 다음 액션을 유도하는 초기 추천 후보입니다.
따라서 현재 구현은 별도 도시 벡터 DB를 운영하지 않고, 설문 응답과 시스템 내부 지역 후보 목록을 조합해 가볍게 추천 결과를 생성합니다.

# 본문

## API 경계

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /api/v1/recommend` |
| 인증 | `x-service-secret` 헤더 필요 |
| 처리 방식 | 요청 접수 후 비동기 작업 실행 |
| 즉시 응답 | `RecommendAckResponse` |
| 콜백 경로 | `{callback_url}/preferences/jobs/{job_id}/result` |

즉시 응답 예시는 다음과 같습니다.

```json
{
  "job_id": "recommend-job-12345",
  "status": "ACCEPTED"
}
```

## 입력값

요청 모델은 `RecommendRequest`입니다.

| 필드 | 타입 | 필수 여부 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | NestJS BullMQ 작업 ID |
| `callback_url` | URL | Yes | 결과를 전달할 NestJS 콜백 베이스 URL |
| `weather` | enum 또는 null | No | 선호 날씨 |
| `travel_range` | enum 또는 null | No | 여행 거리 선호 |
| `travel_style` | enum 또는 null | No | 여행 스타일 |
| `budget_level` | enum 또는 null | No | 예산 선호 |
| `food_personality` | enum list 또는 null | No | 음식 성향 |
| `main_interests` | enum list 또는 null | No | 주요 관심사 |

현재 허용 값은 다음과 같습니다.

| 분류 | 값 |
| --- | --- |
| `weather` | `OCEAN_BEACH`, `SNOW_HOT_SPRING`, `CLEAN_CITY_BREEZE`, `INDOOR_LANDMARK` |
| `travel_range` | `SHORT_HAUL`, `MEDIUM_HAUL`, `LONG_HAUL` |
| `travel_style` | `MODERN_TRENDY`, `HISTORIC_RELAXED`, `PURE_NATURE` |
| `budget_level` | `COST_EFFECTIVE`, `BALANCED`, `PREMIUM_LUXURY` |
| `food_personality` | `LOCAL_HIDDEN_GEM`, `FINE_DINING`, `INSTAGRAMMABLE` |
| `main_interests` | `SHOPPING_TOUR`, `DYNAMIC_ACTIVITY`, `ART_AND_CULTURE` |

## 처리 흐름

1. FastAPI가 `/api/v1/recommend` 요청을 수락하고 비동기 작업을 생성합니다.
2. `RecommendRequest.to_survey()`로 설문 입력을 `SurveyPreference`로 변환합니다.
3. 시스템 내부 `Region` Enum 전체를 추천 후보 목록으로 로드하고 요청마다 후보 순서를 섞습니다.
4. 추천 결과가 매번 과도하게 고정되지 않도록 변주 힌트를 하나 선택합니다.
5. LLM 프롬프트에 설문 응답의 코드와 의미, 후보 지역 목록, 변주 힌트를 함께 전달합니다.
6. LLM은 후보 목록 안에서 중복 없이 정확히 5개의 `region_name`을 JSON으로 반환해야 합니다.
7. 응답 파싱 후 후보 목록 외 지역, 중복 지역, 잘못된 항목을 제거합니다.
8. 결과가 5개보다 적으면 후보 순서에 따라 부족분을 채워 정확히 5개로 정규화합니다.
9. 성공 또는 실패 결과를 콜백 URL로 전송합니다.

## 출력값

성공 콜백 페이로드는 다음 형태입니다.

```json
{
  "status": "SUCCESS",
  "data": {
    "recommended_destinations": [
      { "region_name": "TOKYO" },
      { "region_name": "KYOTO" },
      { "region_name": "SINGAPORE" },
      { "region_name": "PARIS" },
      { "region_name": "BALI" }
    ]
  }
}
```

`recommended_destinations`는 정확히 5개여야 합니다.
각 `region_name`은 `app.schemas.enums.Region`에 정의된 값 중 하나여야 합니다.

## 예외와 실패 처리

| 상황 | 처리 |
| --- | --- |
| LLM 응답 시간 초과 | `FAILED` 콜백, `LLM_TIMEOUT` 오류 코드 전송 |
| LLM 응답 JSON 파싱 실패 | `FAILED` 콜백, `PIPELINE_ERROR` 오류 코드 전송 |
| 후보 정규화 후 5개 미만 | `PIPELINE_ERROR`로 실패 처리 |
| 콜백 전송 실패 | callback delivery retry 정책에 따라 재시도 |

실패 콜백 예시는 다음과 같습니다.

```json
{
  "status": "FAILED",
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "Analysis took too long to complete."
  }
}
```

## 코드 진입점과 검증

| 구분 | 위치 | 확인 내용 |
| --- | --- | --- |
| API 라우터 | `app/api/recommend.py` | `/api/v1/recommend` 요청 수락, 인증 의존성, 비동기 작업 시작 |
| 서비스 | `app/services/recommend_service.py` | 설문 변환, 후보 지역 정규화, LLM 호출, callback payload 생성 |
| 요청/응답 스키마 | `app/schemas/recommend.py` | `RecommendRequest`, `RecommendAckResponse`, callback payload 모델 |
| Enum | `app/schemas/enums.py` | 설문 선택지와 `Region` 후보 목록 |
| 테스트 | `tests/test_recommend_service.py` | 추천 결과 정규화, fallback, 실패 처리 |

# 관련 문서

- [시장 문제와 타겟 사용자](../context/market-and-target-users.md)
- [여행지 추천 API](../api/recommend-api.md)
- [여행지 추천 서버 간 통신 구조](../architecture/recommend-server-communication.md)

# TODO

- 도시 설명 수집, 임베딩, pgvector 기반 추천을 도입할지 별도 아키텍처 문서에서 결정합니다.
- 추천 사유를 사용자에게 함께 전달할 필요가 있으면 `RecommendedDestination` 응답 스키마 확장을 검토합니다.
- 추천 결과 다양성과 재현 가능성 사이의 정책을 제품 요구사항에 맞춰 확정합니다.
