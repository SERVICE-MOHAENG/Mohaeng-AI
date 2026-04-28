---
title: "로드맵 생성 시간 개선안 보고"
status: "review"
author: "@codex"
created_at: 2026-04-28
tags: [reports, roadmap, generation, performance, proposal]
ai_action: "editable"
---

# 요약

7일/8일 로드맵 생성 benchmark 결과, 10개 케이스 모두 현재 기본 전체 timeout 60초를 초과했다.
평균 총 생성 시간은 238.525초이며, 최장 케이스는 342.153초였다.
가장 큰 병목은 `normalize_place_names`, 두 번째 병목은 `synthesize_final_roadmap`으로 확인되었다.

# 기준 측정 결과

- 기준 아티팩트: `artifacts/roadmap-generation/benchmark-before-20260428-065222.json`
- 기준 리포트: `docs/reports/roadmap-generation-performance-baseline.md`
- 성공 케이스: 10/10
- 전체 평균: 238.525초
- 전체 최소/최대: 131.847초 / 342.153초
- 7일 평균: 215.578초
- 8일 평균: 261.472초

| 단계 | 평균(초) | 최소(초) | 최대(초) | 판단 |
| --- | ---: | ---: | ---: | --- |
| `generate_skeleton` | 35.937 | 14.993 | 55.407 | 보조 병목 |
| `fetch_places_from_slots` | 13.567 | 7.544 | 20.632 | 이번 측정의 주 병목 아님 |
| `normalize_place_names` | 115.719 | 6.292 | 180.113 | 1순위 병목 |
| `synthesize_final_roadmap` | 73.300 | 43.182 | 114.457 | 2순위 병목 |

# 개선안

## 1. 장소명 정규화 범위 제한 또는 조건부 생략

- 대상: `normalize_place_names`
- 내용: 번역 후보 수가 많을 때 LLM 정규화 대상을 제한하거나, Google Places `languageCode=ko` 결과를 우선 신뢰해 정규화 단계를 생략한다.
- 추천 방식: 7일 이상 또는 번역 후보가 일정 개수 이상이면 LLM 정규화를 생략하고 원본 `name`을 `display_name`으로 fallback한다.
- 예상 효과: 평균 115.719초 병목을 가장 크게 줄일 수 있다.
- 리스크: 일부 해외 장소명이 영어/현지어로 노출될 수 있다.
- 필요 테스트: display_name fallback, 한글 포함 장소 제외, 고유 place_id 중복 처리 유지.

## 2. 장기 일정의 최종 LLM 후처리 축소

- 대상: `synthesize_final_roadmap`
- 내용: 7일 이상 일정에서 장소 설명 생성 LLM과 방문 시간 제안 LLM을 조건부 fallback 또는 규칙 기반 처리로 전환한다.
- 추천 방식: 장소 description은 기존 fallback 문장을 사용하고, visit_time은 `visit_time_policy` 규칙 기반 결과를 우선 사용한다.
- 예상 효과: 평균 73.300초 병목을 줄일 수 있다.
- 리스크: 장소 설명의 자연스러움이 낮아지고 방문 시간이 덜 개인화될 수 있다.
- 필요 테스트: `CourseResponse` 스키마 유지, description/visit_time 누락 방지, PLANNED/SPONTANEOUS 출력 유지.

## 3. Timeout 정책 분리 및 stage 관측성 강화

- 대상: `generate_service`, `timeout_policy`, roadmap node logging
- 내용: 전체 생성 timeout과 개별 LLM timeout을 분리하고, timeout 실패 시 마지막 완료 stage와 진행 중 stage를 남긴다.
- 추천 방식: 단순 timeout 증가가 아니라 stage별 로그를 먼저 강화하고, 장기 일정 최적화 후 필요한 최소 timeout만 조정한다.
- 예상 효과: timeout 발생 구간을 운영에서 식별할 수 있다.
- 리스크: timeout 값을 과도하게 늘리면 사용자 체감 대기시간이 더 나빠질 수 있다.
- 필요 테스트: timeout callback code 유지, 환경변수 override, stage marker 로그 검증.

## 4. 장기 일정 rerank 조건부 축소

- 대상: `fetch_places_from_slots`, `place_rerank_service`
- 내용: 7일 이상이거나 slot 수가 큰 경우 LLM rerank를 생략하거나 후보 수를 줄인다.
- 판단: 이번 benchmark에서 `fetch_places_from_slots` 평균은 13.567초로 주 병목은 아니므로 1차 개선 우선순위는 낮다.
- 리스크: Google Places 기본 순위 의존도가 증가한다.

## 5. Skeleton 생성 경량화

- 대상: `generate_skeleton`
- 내용: 장기 단일 지역 일정에서 LLM이 모든 slot을 생성하지 않고 section template과 keyword pool을 조합한다.
- 판단: 평균 35.937초로 보조 병목이지만, 1차 개선은 정규화/최종 합성에 집중하는 것이 효과 대비 안전하다.
- 리스크: 일정 다양성이 줄어들 수 있다.

# 추천 승인 범위

1차 개선으로는 다음 3개를 승인받는 것을 추천한다.

1. `normalize_place_names` 장기 일정 조건부 생략 또는 후보 수 제한
2. `synthesize_final_roadmap` 장기 일정 LLM 후처리 축소
3. Timeout stage 관측성 강화

이 조합은 가장 큰 병목 2개를 직접 줄이고, 추후 timeout이 남을 경우 어느 단계에서 발생하는지 관측할 수 있게 한다.
`fetch_places_from_slots`와 skeleton 경량화는 1차 개선 후 재측정 결과를 보고 추가 적용 여부를 결정하는 것이 안전하다.

# 승인 필요 사항

코드 개선은 이 문서의 추천 승인 범위에 대해 사용자 승인을 받은 뒤 진행한다.
승인 후에는 동일 benchmark 스크립트를 다시 실행해 `benchmark-after-*.json`을 생성하고, 개선 전/후 비교 리포트를 작성한다.
