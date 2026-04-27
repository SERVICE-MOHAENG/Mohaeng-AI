---
title: "여행 일정 생성을 위한 AI 파이프라인 및 데이터 소스 선정"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [decisions, adr, roadmap, langgraph, google-places]
ai_action: "editable"
---

# 요약

로드맵 생성 기능은 LangGraph 기반 에이전트 워크플로우와 Google Places API를 중심으로 구현합니다.
LLM은 사용자의 여행 요구사항을 구조화하고 설명을 생성하는 역할을 맡고, 실제 장소 데이터는 Google Places 응답을 우선합니다.
원본 ADR의 선택지는 `E안: 에이전트 오케스트레이션`이었으며, 현재 코드는 그중 상태 기반 그래프, 구조화 출력, Google Places 연동을 우선 구현한 상태입니다.

# 배경

Mohaeng-AI는 사용자의 비정형 여행 요구사항을 실행 가능한 일자별 여행 로드맵으로 변환해야 합니다.
순수 LLM 방식은 존재하지 않는 장소를 추천하거나 좌표를 임의로 생성할 위험이 있고, 단순 선형 파이프라인은 결과가 만족스럽지 않을 때 전체를 다시 생성해야 합니다.
또한 여행 장소 데이터는 폐업, 위치, 최신 리뷰처럼 변동성이 크기 때문에 외부 장소 데이터 소스와의 연동이 필요합니다.

# 본문

## 결정

로드맵 생성 기능은 다음 방향으로 구현합니다.

| 항목 | 결정 |
| --- | --- |
| 워크플로우 구조 | LangGraph 기반 상태 그래프 |
| 장소 데이터 소스 | Google Places API |
| LLM 역할 | 스켈레톤 생성, 장소 설명 생성, 최종 메타데이터 생성 |
| 데이터 검증 | Pydantic 기반 구조화 출력 검증 |
| 장소 좌표 정책 | LLM 생성값이 아니라 Google Places 응답값 사용 |
| 수정 가능성 | 생성 결과를 JSON 상태로 유지해 채팅 수정 기능과 연계 |

현재 로드맵 생성 그래프는 다음 순서로 실행됩니다.

```text
generate_skeleton
-> fetch_places_from_slots
-> normalize_place_names
-> synthesize_final_roadmap
-> END
```

## 검토한 대안

원본 ADR에서는 다음 대안을 비교했습니다.
상세 내용과 다이어그램은 [로드맵 AI 파이프라인 대안 목록](roadmap-generation-ai-pipeline-alternatives.md)을 참고합니다.

| 대안 | 이름 | 판단 |
| --- | --- | --- |
| A안 | API 기반 LLM 어시스턴트 | 구현은 빠르지만 단순 API wrapper에 가까워 확장성이 낮음 |
| B안 | 머신러닝 랭킹 + 알고리즘 | 학습/최적화 경험은 좋지만 데이터 구축 비용이 큼 |
| C안 | LangChain 기반 LLM Native Agent | 최신 기술 활용은 가능하지만 응답 속도와 비용 리스크가 큼 |
| D안 | 알고리즘 엔진 + LLM 에이전트 | 신뢰성과 언어 이해를 함께 확보하지만 인터페이스 복잡도가 큼 |
| E안 | 에이전트 오케스트레이션 | 상태 관리와 부분 수정 가능성이 가장 커서 채택 |

## 채택 이유

> [!IMPORTANT]
> 로드맵 생성 결과는 단순 텍스트가 아니라 이후 수정 가능한 JSON 상태여야 합니다.

E안은 생성, 검증, 보정, 수정 요청 처리까지 확장할 수 있는 구조입니다.
LangGraph는 각 단계를 노드로 분리하고 상태를 전달할 수 있어 로드맵 생성과 채팅 수정 기능의 공통 기반으로 적합합니다.
Google Places API는 장소명, 주소, 좌표, Google Maps URL 등 사용자에게 직접 노출되는 데이터의 신뢰도를 높이는 데 필요합니다.

## 현재 구현 반영 상태

현재 코드에 반영된 항목은 다음과 같습니다.

- LangGraph `StateGraph` 기반 로드맵 생성 워크플로우
- Pydantic 기반 요청/응답 및 LLM 출력 검증
- Google Places API 기반 장소 검색
- 지역 bbox를 활용한 장소 검색 restriction/bias/fallback
- LLM rerank를 통한 장소 후보 선택
- 장소 설명과 최종 로드맵 메타데이터 생성
- 안전한 `next_action_suggestion` 주입
- 비동기 요청 수락 후 NestJS 콜백으로 결과 전달

원본 ADR에는 포함되어 있으나 현재 구현되지 않았거나 제한적으로 반영된 항목은 다음과 같습니다.

| 항목 | 현재 상태 |
| --- | --- |
| TSP 기반 경로 최적화 | 구현되어 있지 않음 |
| K-Means 또는 클러스터링 기반 일자 분배 | 구현되어 있지 않음 |
| 숙소 anchor 기반 일정 배치 | 구현되어 있지 않음 |
| 자체 Vector DB/RAG 장소 검색 | 구현되어 있지 않음 |
| Google Places 캐싱 서버 | 구현되어 있지 않음 |
| 실제 저장 API 호출 | Python 워커는 callback 전달까지만 담당 |

## 결과

긍정적 효과는 다음과 같습니다.

- 로드맵 생성 단계를 명시적인 그래프 노드로 나눠 확장하기 쉬워졌습니다.
- 장소 데이터는 Google Places를 기준으로 확보해 좌표 환각 가능성을 줄였습니다.
- 생성 결과가 구조화된 JSON이므로 채팅 수정 기능과 연결하기 쉽습니다.
- 실패 시 단계별 로그와 Discord 웹훅 알림으로 운영 관찰성이 높아졌습니다.

부정적 효과와 대응은 다음과 같습니다.

- Google Places API 비용이 발생합니다. 현재는 검색 fallback과 후보 수 제한으로 호출 범위를 관리합니다.
- LangGraph와 LLM 호출이 결합되어 구현 복잡도가 높습니다. 노드 단위 책임을 분리하고 Pydantic 검증으로 안정성을 확보합니다.
- 원본 ADR의 수학적 최적화 요소가 아직 구현되지 않았습니다. 필요한 경우 별도 ADR에서 도입 여부를 다시 결정합니다.

# TODO

- TSP, 클러스터링, 숙소 anchor 전략을 실제 제품 요구사항에 따라 도입할지 결정합니다.
- Google Places 캐싱 전략이 필요하면 비용, 최신성, 무효화 정책을 포함한 별도 ADR을 작성합니다.
- 현재 구현과 원본 E안 사이의 차이가 커지면 이 ADR의 status 또는 후속 ADR로 결정 이력을 갱신합니다.
