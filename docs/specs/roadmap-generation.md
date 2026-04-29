---
title: "로드맵 생성 기능"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [specs, roadmap, generation, langgraph, google-places]
ai_action: "editable"
---

# 요약

로드맵 생성 기능은 사용자의 여행 기간, 지역, 동행자, 테마, 여행 성향을 받아 실행 가능한 일자별 여행 로드맵을 생성합니다.
API는 `/api/v1/generate`이며, 요청을 즉시 수락한 뒤 LangGraph 기반 파이프라인을 비동기로 실행하고 콜백으로 결과를 전달합니다.
현재 구현은 스켈레톤 생성, Google Places 검색, 최종 로드맵 합성 단계를 거칩니다.

# 배경

사용자는 추상적인 여행 취향과 기간만으로 바로 실행 가능한 여행 계획을 얻고자 합니다.
로드맵 생성 기능은 LLM의 계획 생성 능력과 Google Places의 실제 장소 데이터를 결합해, 장소명, 주소, 좌표, 방문 순서를 포함한 구조화된 결과를 만듭니다.
LLM이 좌표를 직접 생성하지 않고 Google Places 응답을 우선 사용하도록 하여 장소 데이터의 신뢰도를 높입니다.

# 본문

## API 경계

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /api/v1/generate` |
| 인증 | `x-service-secret` 헤더 필요 |
| 처리 방식 | 요청 접수 후 비동기 작업 실행 |
| 즉시 응답 | `GenerateAckResponse` |
| 콜백 경로 | `{callback_url}/itineraries/{job_id}/result` |

즉시 응답 예시는 다음과 같습니다.

```json
{
  "job_id": "generate-job-12345",
  "status": "ACCEPTED"
}
```

## 입력값

요청 모델은 `GenerateRequest`이며, 실제 로드맵 생성 입력은 `payload`의 `CourseRequest`입니다.

| 필드 | 타입 | 필수 여부 | 설명 |
| --- | --- | --- | --- |
| `job_id` | string | Yes | NestJS가 발급한 작업 ID |
| `callback_url` | URL | Yes | 결과 콜백을 받을 NestJS URL |
| `payload.start_date` | date | Yes | 전체 여행 시작일 |
| `payload.end_date` | date | Yes | 전체 여행 종료일 |
| `payload.regions` | `RegionDateRange[]` | Yes | 지역별 여행 기간, 최대 8개 |
| `payload.people_count` | integer | Yes | 총 인원 수, 1~20 |
| `payload.companion_type` | `CompanionType[]` | Yes | 동행자 유형, 1개 이상 |
| `payload.travel_themes` | `TravelTheme[]` | Yes | 여행 테마, 1개 이상 |
| `payload.pace_preference` | `PacePreference` | Yes | 일정 밀도 선호 |
| `payload.planning_preference` | `PlanningPreference` | Yes | 계획형/즉흥형 선호 |
| `payload.destination_preference` | `DestinationPreference` | Yes | 관광지/로컬 선호 |
| `payload.activity_preference` | `ActivityPreference` | Yes | 활동/휴식 선호 |
| `payload.priority_preference` | `PriorityPreference` | Yes | 효율/감성 우선순위 |
| `payload.notes` | string 또는 null | No | 추가 요청 사항 |

현재 `CourseRequest`에는 `budget_range` 필드가 없습니다.

## 입력 검증 규칙

- `end_date`는 `start_date`와 같거나 이후여야 합니다.
- 전체 여행 기간은 최대 8일이어야 합니다.
- 각 지역 구간의 `end_date`는 해당 `start_date`와 같거나 이후여야 합니다.
- 각 지역 구간은 전체 여행 기간 안에 포함되어야 합니다.
- `payload.regions`는 최대 8개까지 허용합니다.
- 스켈레톤 생성 단계에서 지역 구간 사이 날짜 공백과 겹침을 검증합니다.
- 지역 구간을 정렬했을 때 전체 여행 기간을 빠짐없이 덮어야 합니다.
- `people_count`는 1명 이상 20명 이하입니다.
- `companion_type`과 `travel_themes`는 각각 최소 1개 이상이어야 합니다.

## 처리 흐름

LangGraph 워크플로우는 다음 노드 순서로 실행됩니다.

```text
generate_skeleton
-> fetch_places_from_slots
-> synthesize_final_roadmap
-> END
```

### 1. `generate_skeleton`

`CourseRequest`를 바탕으로 지역 구간별 일자와 슬롯을 생성합니다.
LLM은 특정 상호명 대신 `section`, `area`, `keyword` 중심의 검색용 스켈레톤을 생성합니다.

일정 밀도별 슬롯 범위는 현재 다음과 같습니다.

| `pace_preference` | 슬롯 수 |
| --- | --- |
| `DENSE` | 일자별 6~7개 |
| `RELAXED` | 일자별 4~5개 |
| 기타 또는 누락 | 일자별 5~6개 |

스켈레톤은 Pydantic 파서로 검증하며, 실패 시 복구 프롬프트와 자동 보정 로직을 사용합니다.
검증 항목에는 슬롯 수, region 일치 여부, 허용 section, area/keyword 존재 여부, 검색에 불리한 좌표/전화번호/상세 주소 패턴 제거가 포함됩니다.

### 2. `fetch_places_from_slots`

스켈레톤 슬롯의 `area`와 `keyword`로 Google Places Text Search를 수행합니다.
슬롯 검색은 `asyncio.gather`로 병렬 실행됩니다.

검색에는 다음 정책을 적용합니다.

- 지역 bbox가 있으면 location restriction을 우선 사용합니다.
- restriction 검색 결과가 없으면 location bias로 재검색합니다.
- 그래도 결과가 없으면 지역명을 붙인 쿼리로 unfiltered 검색을 수행합니다.
- 마지막 fallback에서는 최소 평점 필터를 해제할 수 있습니다.
- `GOOGLE_PLACES_MIN_RATING`, `GOOGLE_PLACES_LLM_RERANK_ENABLED`, `GOOGLE_PLACES_LLM_RERANK_MAX_CANDIDATES` 설정을 반영합니다.
- LLM rerank가 켜져 있으면 일자별 후보 중 슬롯에 가장 적합한 `place_id`를 선택해 우선순위를 조정합니다.

### 3. `synthesize_final_roadmap`

확정된 장소 목록을 바탕으로 최종 응답을 조립합니다.

이 단계에서 수행하는 작업은 다음과 같습니다.

- 장소별 한 줄 설명을 LLM으로 생성합니다.
- 설명 생성 실패 또는 타임아웃 시 기본 설명을 적용합니다.
- `visit_time`은 스켈레톤의 section 값을 기준으로 대략적인 시각에 정적 매핑합니다.
- section 매핑은 `MORNING=09:00`, `LUNCH=12:00`, `AFTERNOON=14:00`, `DINNER=18:00`, `EVENING=20:00`, `NIGHT=22:00`입니다.
- 알 수 없는 section은 `09:00`으로 fallback합니다.
- LLM으로 `title`, `summary`, `tags`, `llm_commentary`를 생성합니다.
- `next_action_suggestion`은 LLM 결과를 그대로 쓰지 않고 시스템에서 지원 가능한 문장만 안전하게 주입합니다.
- `CourseResponse` 스키마로 최종 검증합니다.

## 출력값

성공 콜백 페이로드는 다음 형태입니다.

```json
{
  "status": "SUCCESS",
  "data": {
    "start_date": "2026-04-10",
    "end_date": "2026-04-15",
    "trip_days": 6,
    "nights": 5,
    "people_count": 2,
    "tags": ["미식", "문화", "감성"],
    "title": "도쿄 감성 여행",
    "summary": "로컬 감성과 미식을 중심으로 구성한 여유로운 여행입니다.",
    "itinerary": [],
    "llm_commentary": "이 코스는 사용자의 테마와 이동 흐름을 고려해 구성했습니다.",
    "next_action_suggestion": []
  }
}
```

`itinerary`는 `DailyItinerary[]`이며 각 일자는 `CoursePlace[]`를 포함합니다.
각 장소에는 `place_name`, `place_id`, `address`, `latitude`, `longitude`, `place_url`, `description`, `visit_sequence`, `visit_time`이 포함됩니다.

## 예외와 실패 처리

| 상황 | 처리 |
| --- | --- |
| 요청 스키마 검증 실패 | FastAPI/Pydantic 검증 오류 |
| 스켈레톤 생성/복구 실패 | `FAILED` 콜백, `PIPELINE_ERROR` |
| Google Places 서비스 초기화 실패 | 그래프 상태에 error 기록 후 실패 |
| 최종 로드맵 누락 | `PIPELINE_ERROR` |
| 전체 처리 시간 초과 | `FAILED` 콜백, `LLM_TIMEOUT` |
| 콜백 전송 실패 | callback delivery retry 정책에 따라 재시도 |

## 원본 문서 대비 현재 구현 차이

> [!NOTE]
> 원본 문서에는 `budget_range` 기반 Google Places price level 매핑, 카테고리별 체류 시간, Google Routes API 전제 등이 포함되어 있었습니다.
> 현재 코드의 `CourseRequest`에는 `budget_range`가 없고, 실제 이동 시간은 공용 visit time policy와 LLM 제안을 조합해 처리합니다.
> 이 문서는 현재 구현된 필드와 파이프라인을 기준으로 작성합니다.

## 코드 진입점과 검증

| 구분 | 위치 | 확인 내용 |
| --- | --- | --- |
| API 라우터 | `app/api/generate.py` | `/api/v1/generate` 요청 수락, 인증 의존성, 비동기 작업 시작 |
| 서비스 | `app/services/generate_service.py` | 생성 그래프 실행, timeout 처리, callback payload 생성 |
| 그래프 정의 | `app/graph/roadmap/workflow.py` | LangGraph 노드 연결과 실행 순서 |
| 그래프 노드 | `app/graph/roadmap/nodes/` | 스켈레톤 생성, 장소 검색, 최종 합성 |
| 장소 검색 | `app/services/google_places_service.py`, `app/services/places_service.py`, `app/services/place_rerank_service.py` | Google Places 호출, fallback, rerank 정책 |
| 요청/응답 스키마 | `app/schemas/generate.py`, `app/schemas/course.py`, `app/schemas/skeleton.py`, `app/schemas/place.py` | 생성 요청, 최종 로드맵, 중간 스켈레톤, 장소 모델 |
| 공통 정책 | `app/core/timeout_policy.py` | timeout 분류 |
| 테스트 | `tests/test_roadmap_generation_simplified_pipeline.py`, `tests/test_timeout_policy.py` | 단순화된 생성 파이프라인, timeout 정책 |

# 관련 문서

- [모행 프로젝트 개요](../context/project-overview.md)
- [여행 일정 생성을 위한 AI 파이프라인 및 데이터 소스 선정](../decisions/roadmap-generation-ai-pipeline.md)
- [로드맵 생성 API](../api/generate-api.md)
- [로드맵 생성 서버 간 통신 구조](../architecture/roadmap-generation-server-communication.md)

# TODO

- 예산 기반 장소 필터링이 필요하면 `CourseRequest` 스키마와 Google Places 검색 정책을 함께 확장합니다.
- 실제 대중교통 이동 시간 또는 경로가 필요하면 Google Routes API 도입 여부를 별도 결정합니다.
