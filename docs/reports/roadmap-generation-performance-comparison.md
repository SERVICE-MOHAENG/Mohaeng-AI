---
title: "로드맵 생성 시간 개선 전후 비교 리포트"
status: "review"
author: "@codex"
created_at: 2026-04-29
tags: [reports, roadmap, generation, performance, comparison]
ai_action: "editable"
---

# 요약

장소명 정규화 단계를 제거하고 방문 시간 계산을 section 기반 정적 매핑으로 변경한 뒤 동일한 10개 장기 일정 benchmark를 다시 실행했다.
전체 평균 생성 시간은 238.525초에서 82.571초로 65.4% 개선되었다.
하지만 개선 후에도 10개 중 8개 케이스가 현재 기본 전체 timeout 60초를 초과했다.
이번 개선은 제품 품질 저하를 크게 만들지 않는 선에서 병목을 제거한 1차 성능 개선으로 종료하고, 남은 차이는 timeout 기본값과 프로덕션 운영값을 현실화해 대응한다.

# 측정 아티팩트

| 구분 | 파일 | 상태 |
| --- | --- | --- |
| 개선 전 | `artifacts/roadmap-generation/benchmark-before-20260428-065222.json` | `COMPLETED` |
| 개선 후 | `artifacts/roadmap-generation/benchmark-after-20260428-implementation.json` | `COMPLETED` |

두 benchmark 모두 동일한 7일 5건, 8일 5건 케이스를 사용했다.

# 전체 비교

| 항목 | 개선 전 | 개선 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 총 시간 | 238.525초 | 82.571초 | -65.4% |
| 최소 총 시간 | 131.847초 | 41.130초 | -68.8% |
| 최대 총 시간 | 342.153초 | 145.747초 | -57.4% |
| 7일 평균 | 215.578초 | 91.210초 | -57.7% |
| 8일 평균 | 261.472초 | 73.932초 | -71.7% |
| 60초 이상 케이스 | 10/10 | 8/10 | -2건 |
| 48초 이상 케이스 | 10/10 | 9/10 | -1건 |

# 케이스별 비교

| case_id | 일수 | 개선 전(초) | 개선 후(초) | 변화(초) | 개선율 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `seven_days_seoul` | 7 | 131.847 | 145.747 | +13.900 | -10.5% |
| `seven_days_san_francisco` | 7 | 281.558 | 112.157 | -169.401 | 60.2% |
| `seven_days_vancouver` | 7 | 138.019 | 66.451 | -71.568 | 51.9% |
| `seven_days_sydney` | 7 | 288.586 | 71.496 | -217.090 | 75.2% |
| `seven_days_paris` | 7 | 237.878 | 60.201 | -177.677 | 74.7% |
| `eight_days_tokyo` | 8 | 326.538 | 76.769 | -249.769 | 76.5% |
| `eight_days_london` | 8 | 174.829 | 55.018 | -119.811 | 68.5% |
| `eight_days_new_york_city` | 8 | 342.153 | 117.711 | -224.442 | 65.6% |
| `eight_days_bangkok` | 8 | 276.347 | 79.030 | -197.317 | 71.4% |
| `eight_days_singapore` | 8 | 187.491 | 41.130 | -146.361 | 78.1% |

`seven_days_seoul`은 개선 후 더 느려졌다.
아티팩트 로그상 skeleton 생성이 2회 시도 및 autofix를 거치며 79.091초를 사용했다.
이는 제거한 단계와 무관한 skeleton LLM 변동성으로 판단한다.

# 단계별 비교

| 단계 | 개선 전 평균 | 개선 후 평균 | 판단 |
| --- | ---: | ---: | --- |
| `generate_skeleton` | 35.937초 | 34.351초 | 거의 동일 |
| `fetch_places_from_slots` | 13.567초 | 12.143초 | 거의 동일 |
| `normalize_place_names` | 115.719초 | 제거됨 | 병목 제거 |
| `synthesize_final_roadmap` | 73.300초 | 36.077초 | 50.8% 개선 |

개선 효과는 주로 `normalize_place_names` 제거와 방문 시간 계산 제거에서 발생했다.
`synthesize_final_roadmap`은 아직 장소 설명 LLM과 최종 요약 LLM을 포함하므로 평균 36.077초가 남아 있다.

# 남은 병목과 리스크

개선 후에도 60초 초과 케이스가 8개 남았다.
현재 남은 주요 병목은 다음이다.

1. `generate_skeleton`
   - 개선 후 평균 34.351초다.
   - repair/autofix가 발생하면 단일 단계가 60초 이상까지 증가할 수 있다.
   - `seven_days_seoul`은 skeleton 단계만 79.091초였다.

2. `synthesize_final_roadmap`
   - 개선 후 평균 36.077초다.
   - 장소 설명 LLM과 최종 summary LLM이 남아 있다.

3. `fetch_places_from_slots`
   - 평균은 12.143초로 낮지만, rerank LLM과 fallback에 따라 변동 가능성이 있다.

# Timeout 정책 제안

현재 기본 전체 timeout 60초는 7~8일 장기 일정 생성에는 현실적으로 맞지 않는다.
개선 후 평균은 82.571초이고, 최대는 145.747초다.
따라서 60초 제한을 유지하면 장기 일정의 상당수가 정상 생성 가능함에도 timeout 실패로 처리될 수 있다.

## 기본값 변경 반영

개발/기본 설정의 `LLM_TIMEOUT_SECONDS` 기본값은 60초에서 180초로 변경한다.

| 항목 | 기존 | 변경 |
| --- | ---: | ---: |
| `REQUEST_TIMEOUT_SECONDS` | 60초 | 180초 |
| `LLM_TIMEOUT_SECONDS` | 60초 | 180초 |

180초는 개선 후 최대 측정값 145.747초에 약 23.5%의 여유를 둔 값이다.
timeout policy는 `LLM_TIMEOUT_SECONDS`가 `REQUEST_TIMEOUT_SECONDS` 상한을 넘지 못하므로 두 값을 함께 조정한다.

## 프로덕션 보수 추천값

실제 프로덕션 환경에서는 외부 API latency, OpenAI 응답 변동성, Google Places fallback 증가, 동시 처리 부하를 고려해 더 보수적인 값을 권장한다.

| 환경 | `REQUEST_TIMEOUT_SECONDS` | `LLM_TIMEOUT_SECONDS` | 이유 |
| --- | ---: | ---: | --- |
| local/dev | 180초 | 180초 | 장기 일정 benchmark 최대값을 커버 |
| staging | 240초 | 240초 | 외부 API 변동성과 재현 테스트 여유 확보 |
| production | 300초 | 300초 | p95/p99 변동성과 운영 부하를 고려한 보수값 |

프로덕션 추천값은 300초다.
개선 후 최대값 145.747초의 약 2배 수준으로, 장기 일정 생성의 우발적 timeout을 줄이면서도 무제한 대기를 허용하지 않는 절충값이다.

## 운영상 주의 사항

- timeout 값을 늘리는 것은 성능 개선의 대체가 아니라 장기 작업 특성에 맞는 실패 기준 조정이다.
- `/api/v1/generate`는 비동기 ACK 후 callback 구조이므로, 클라이언트 동기 대기 시간이 300초로 늘어나는 구조는 아니다.
- timeout 상향 후에도 callback 실패, OpenAI 장애, Google Places 장애는 별도 실패로 처리되어야 한다.
- 운영에서는 timeout 발생 건수, 전체 생성 시간, skeleton retry 여부, finalization 시간을 함께 모니터링해야 한다.

# 결론

이번 변경은 평균 시간을 65.4% 줄여 명확한 효과가 있었다.
제품 품질과 구현 리스크를 고려하면 이번 성능 개선은 이 수준에서 마무리하는 것이 적절하다.
후속 조치는 추가 최적화보다 timeout 기본값을 180초로 운영하고, 프로덕션에서는 300초를 사용하는 방향이 현실적이다.
추가 최적화가 필요해지는 경우에는 skeleton retry 감소, 장소 설명 LLM 축소, rerank 조건부 축소를 별도 이슈로 다룬다.
