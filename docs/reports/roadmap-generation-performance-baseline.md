---
title: "로드맵 생성 장기 일정 성능 기준 리포트"
status: "review"
author: "@codex"
created_at: 2026-04-28
tags: [reports, roadmap, generation, performance, timeout]
ai_action: "editable"
---

# 요약

로드맵 생성 Timeout 문제를 분석하기 위해 7일 일정 5건, 8일 일정 5건을 대상으로 단계별 실행 시간을 측정했다.
10개 케이스는 모두 성공했지만 총 소요 시간이 131.847초~342.153초로 모두 현재 기본 전체 timeout 60초를 초과했다.
가장 큰 병목은 `normalize_place_names`였고, 10건 중 9건에서 전체 시간의 43.0%~61.9%를 차지했다.

# 배경

운영 중 긴 로드맵 생성 요청, 특히 7일과 8일 일정에서 생성 시간이 길고 `TIMEOUT` 제한에 걸리는 현상이 확인되었다.
현재 생성 파이프라인은 다음 순서로 실행된다.

```text
generate_skeleton
-> fetch_places_from_slots
-> normalize_place_names
-> synthesize_final_roadmap
```

전체 생성은 `LLM_TIMEOUT_SECONDS` 안에 완료되어야 하며, 문서와 `.env.example`의 기본값은 60초다.
긴 일정에서는 일수 증가에 따라 skeleton slot 수, Google Places 검색 수, rerank 입력 크기, 장소명 정규화 후보 수, 최종 설명/요약 LLM 입력 크기가 함께 증가한다.

# 측정 아티팩트

- 스크립트: `tools/benchmark_roadmap_generation.py`
- 생성 아티팩트: `artifacts/roadmap-generation/benchmark-before-20260428-065222.json`
- 실행 명령: `docker exec mohaeng python tools/benchmark_roadmap_generation.py --case-timeout-seconds 600`
- 실행 상태: `COMPLETED`
- 성공 케이스: 10/10

필수 환경변수 상태는 다음과 같다.

| 환경변수 | 존재 여부 |
| --- | --- |
| `OPENAI_API_KEY` | true |
| `GOOGLE_PLACES_API_KEY` | true |
| `SERVICE_SECRET` | true |
| `HMAC_SECRET` | true |

# Benchmark 케이스

총 10개 케이스를 고정 입력으로 구성했다.

| 구분 | case_id | 지역 | 일수 | pace | planning |
| --- | --- | --- | --- | --- | --- |
| 7일 | `seven_days_seoul` | `SEOUL` | 7 | `DENSE` | `PLANNED` |
| 7일 | `seven_days_san_francisco` | `SAN_FRANCISCO` | 7 | `DENSE` | `PLANNED` |
| 7일 | `seven_days_vancouver` | `VANCOUVER` | 7 | `RELAXED` | `PLANNED` |
| 7일 | `seven_days_sydney` | `SYDNEY` | 7 | `DENSE` | `SPONTANEOUS` |
| 7일 | `seven_days_paris` | `PARIS` | 7 | `RELAXED` | `PLANNED` |
| 8일 | `eight_days_tokyo` | `TOKYO` | 8 | `DENSE` | `PLANNED` |
| 8일 | `eight_days_london` | `LONDON` | 8 | `RELAXED` | `PLANNED` |
| 8일 | `eight_days_new_york_city` | `NEW_YORK_CITY` | 8 | `DENSE` | `SPONTANEOUS` |
| 8일 | `eight_days_bangkok` | `BANGKOK` | 8 | `DENSE` | `PLANNED` |
| 8일 | `eight_days_singapore` | `SINGAPORE` | 8 | `RELAXED` | `PLANNED` |

# 측정 항목

스크립트는 실제 환경변수가 준비되면 각 케이스마다 다음 값을 JSON으로 남긴다.

| 항목 | 설명 |
| --- | --- |
| `durations_seconds.generate_skeleton` | skeleton 생성 LLM 호출 및 검증/복구 시간 |
| `durations_seconds.fetch_places_from_slots` | slot별 Google Places 검색 및 optional rerank 시간 |
| `durations_seconds.normalize_place_names` | 장소명 한국어 표시 정규화 LLM 시간 |
| `durations_seconds.synthesize_final_roadmap` | 장소 설명, 방문 시간, 최종 요약 생성 시간 |
| `total_seconds` | 전체 파이프라인 실행 시간 |
| `summary.slot_count` | skeleton slot 총 개수 |
| `summary.empty_place_slot_count` | 장소 조회 결과가 비어 있는 slot 개수 |
| `summary.final_place_count` | 최종 로드맵에 포함된 장소 개수 |
| `job_logs` | 기존 `append_job_log` 기반 단계별 상세 로그 |

Timeout 위험도는 현재 기본 제한인 60초 기준으로 판단한다.

| 기준 | 의미 |
| --- | --- |
| `total_seconds >= 48` | 60초 제한의 80% 이상으로 timeout 위험 |
| `total_seconds >= 60` | 현재 기본 제한 초과 |
| 특정 단계가 전체 시간의 40% 이상 | 해당 단계 우선 개선 후보 |

# 측정 결과

## 전체 결과

| case_id | 일수 | slot | 빈 slot | 총 시간(초) | 최장 단계 | 최장 단계 비중 |
| --- | --- | --- | --- | --- | --- | --- |
| `seven_days_seoul` | 7 | 47 | 0 | 131.847 | `synthesize_final_roadmap` | 50.9% |
| `seven_days_san_francisco` | 7 | 47 | 1 | 281.558 | `normalize_place_names` | 54.1% |
| `seven_days_vancouver` | 7 | 33 | 4 | 138.019 | `normalize_place_names` | 46.6% |
| `seven_days_sydney` | 7 | 47 | 0 | 288.586 | `normalize_place_names` | 43.0% |
| `seven_days_paris` | 7 | 33 | 0 | 237.878 | `normalize_place_names` | 61.9% |
| `eight_days_tokyo` | 8 | 54 | 0 | 326.538 | `normalize_place_names` | 47.0% |
| `eight_days_london` | 8 | 38 | 0 | 174.829 | `normalize_place_names` | 50.1% |
| `eight_days_new_york_city` | 8 | 54 | 0 | 342.153 | `normalize_place_names` | 52.6% |
| `eight_days_bangkok` | 8 | 54 | 3 | 276.347 | `normalize_place_names` | 46.7% |
| `eight_days_singapore` | 8 | 38 | 0 | 187.491 | `normalize_place_names` | 60.1% |

## 요약 통계

| 항목 | 평균(초) | 최소(초) | 최대(초) |
| --- | ---: | ---: | ---: |
| 전체 | 238.525 | 131.847 | 342.153 |
| `generate_skeleton` | 35.937 | 14.993 | 55.407 |
| `fetch_places_from_slots` | 13.567 | 7.544 | 20.632 |
| `normalize_place_names` | 115.719 | 6.292 | 180.113 |
| `synthesize_final_roadmap` | 73.300 | 43.182 | 114.457 |

| 일정 길이 | 평균 총 시간(초) | 최대 총 시간(초) |
| --- | ---: | ---: |
| 7일 | 215.578 | 288.586 |
| 8일 | 261.472 | 342.153 |

## Timeout 판정

모든 케이스가 현재 기본 전체 제한 60초를 초과했다.
가장 빠른 케이스인 `seven_days_seoul`도 131.847초로 60초의 219.7% 수준이다.
가장 느린 케이스인 `eight_days_new_york_city`는 342.153초로 60초의 570.3% 수준이다.

# 병목 분석

실측 기준 병목 우선순위는 다음과 같다.

1. `normalize_place_names`
   - 평균 115.719초로 전체 단계 중 가장 느리다.
   - 10건 중 9건에서 최장 단계였다.
   - 해외 도시에서 한글이 없는 장소명이 대량 발생하면 모든 고유 장소명을 한 번에 LLM 정규화한다.
   - 최악 케이스는 `eight_days_new_york_city`의 180.113초다.

2. `synthesize_final_roadmap`
   - 평균 73.300초로 두 번째 병목이다.
   - `_fill_place_descriptions_with_llm`가 전체 일자/장소 목록을 한 번에 LLM에 전달한다.
   - `_apply_visit_time_for_daily_places`에서 방문 시간 제안을 위해 추가 LLM 호출이 발생한다.
   - `ROADMAP_SUMMARY`가 긴 itinerary context를 다시 입력으로 받아 최종 메타데이터를 생성한다.
   - 최악 케이스는 `seven_days_sydney`의 114.457초다.

3. `generate_skeleton`
   - 평균 35.937초다.
   - 지역 구간별로 skeleton LLM을 호출한다.
   - 단일 지역 7~8일 케이스는 호출 수가 1회지만, 검증 실패 시 repair LLM 호출이 추가된다.
   - 최악 케이스는 `eight_days_tokyo`의 55.407초로, 이 단계만으로도 60초 제한에 근접한다.

4. `fetch_places_from_slots`
   - 평균 13.567초로 이번 측정에서는 주 병목이 아니다.
   - DENSE 7~8일 일정은 slot 수가 47~54개였지만 병렬 검색 덕분에 7.544초~20.632초 범위에 머물렀다.
   - 다만 Google Places API latency나 fallback 증가가 발생하면 운영 환경에서는 변동성이 커질 수 있다.

# Timeout 가능성이 높은 구간

현재 가장 위험한 지점은 전체 파이프라인을 하나의 `LLM_TIMEOUT_SECONDS`로 감싼 구조다.
실측 결과 10개 케이스 모두 60초를 초과했기 때문에, 운영에서 7~8일 생성 요청은 정상 성공보다 timeout 실패 가능성이 높다.

특히 다음 조합은 timeout 가능성이 높다.

- DENSE 8일 일정
- 해외 도시처럼 장소명 정규화 후보가 많은 일정
- rerank가 켜져 있고 일자별 후보 수가 많은 일정
- `PLANNED` 일정으로 visit time LLM과 정책 적용이 모두 수행되는 일정

# 승인 필요 개선안

아래 개선안은 실제 성능 개선 코드 작성 전 사용자 승인이 필요하다.

## 1. 장소명 정규화 범위 제한 또는 제거

- 대상: `normalize_place_names`
- 내용: 번역 후보 수가 많을 때 상위 N개만 LLM 정규화하고 나머지는 원문 fallback을 사용하거나, Google Places `languageCode=ko` 결과를 우선 신뢰해 정규화 단계를 생략한다.
- 예상 효과: 평균 115.719초 병목을 크게 줄일 수 있다.
- 품질 리스크: 일부 장소명이 영어/현지어로 노출될 수 있다.
- 테스트: display_name fallback, 한글 포함 장소 제외, 고유 place_id 중복 제거 유지.

## 2. 장기 일정의 최종 LLM 후처리 축소

- 대상: `synthesize_final_roadmap`
- 내용: 장소 설명과 방문 시간 제안 LLM을 장기 일정에서 조건부 fallback 또는 규칙 기반 처리로 전환한다.
- 예상 효과: 평균 73.300초 병목 감소.
- 품질 리스크: 장소별 설명이 덜 자연스럽거나 방문 시간이 더 규칙 기반으로 보일 수 있다.
- 테스트: 최종 `CourseResponse` 스키마 유지, description/visit_time 누락 방지, 7~8일 케이스 fallback 검증.

## 3. 장기 일정 rerank 조건부 비활성화 또는 축소

- 대상: `fetch_places_from_slots`, `place_rerank_service`
- 내용: 7일 이상이거나 slot 수가 특정 기준 이상이면 LLM rerank를 생략하거나 후보 수를 축소한다.
- 예상 효과: 일자별 rerank LLM 호출 시간 감소.
- 품질 리스크: Google Places 기본 순위 의존도가 증가한다.
- 테스트: rerank on/off 결과 안정성, fallback_used 로그, 장소 순서 유지 검증.

## 4. Skeleton 생성 경량화

- 대상: `generate_skeleton`
- 내용: 7~8일 단일 지역 일정은 LLM이 모든 slot을 직접 생성하지 않고, 날짜별 section template과 지역/테마 기반 keyword pool을 조합하는 하이브리드 방식으로 전환한다.
- 예상 효과: 평균 35.937초 감소, repair 호출 가능성 감소.
- 품질 리스크: skeleton 다양성이 감소할 수 있다.
- 테스트: slot 수/section/region 검증, DENSE/RELAXED slot target 유지, 최종 생성 성공 여부 검증.

## 5. Timeout 정책 분리

- 대상: `generate_service`, `timeout_policy`
- 내용: 전체 생성 timeout과 개별 LLM timeout을 분리하고, timeout 실패 시 마지막 완료 stage를 알 수 있도록 stage marker를 남긴다.
- 예상 효과: 운영 관측성 개선과 원인 식별 개선.
- 품질 리스크: timeout 값을 단순히 늘리면 사용자 대기 시간이 더 길어질 수 있으므로 성능 개선과 함께 적용해야 한다.
- 테스트: timeout policy 기본값/환경변수 override, timeout callback code 유지, stage별 로그 검증.

# 다음 단계

위 개선안 중 적용할 항목을 사용자에게 보고하고 승인받은 뒤 코드 개선을 시작한다.
현재 데이터만 보면 1순위는 `normalize_place_names` 축소, 2순위는 `synthesize_final_roadmap` 후처리 축소다.
