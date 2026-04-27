---
title: "기술 스택"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [architecture, tech-stack, fastapi, langgraph, openai]
ai_action: "editable"
---

# 요약

Mohaeng-AI는 Python 3.12 기반 FastAPI 서비스로, 여행 로드맵 생성과 채팅 기반 로드맵 수정을 담당합니다.
핵심 AI 워크플로우는 LangGraph로 구성하며, LLM 호출은 OpenAI Chat Completions 계열 모델을 사용합니다.
장소 데이터는 선택적으로 Google Places API를 사용하고, 요청/응답 경계와 LLM 출력 검증에는 Pydantic을 사용합니다.

# 배경

Mohaeng-AI는 외부 LLM과 장소 검색 API를 호출해 여행 계획을 생성하거나 수정합니다.
이 특성상 비동기 API 처리, 명확한 스키마 검증, LLM 응답의 구조화, 외부 API 타임아웃 관리가 중요합니다.
기술 선택은 Python AI 생태계, LangGraph 지원 여부, FastAPI 기반 API 서버 구성, Pydantic 기반 데이터 검증을 중심으로 이루어졌습니다.

# 본문

## 현재 적용된 핵심 기술

| 분류 | 선정 기술 | 역할 |
| --- | --- | --- |
| 프로그래밍 언어 | Python 3.12 | AI 워크플로우, 데이터 검증, 외부 API 연동 구현 |
| API 서버 | FastAPI | AI 기능을 HTTP API로 제공하고 비동기 요청 처리를 지원 |
| 에이전트/그래프 프레임워크 | LangGraph | 로드맵 생성 및 채팅 수정 흐름을 상태 기반 그래프로 구성 |
| LLM 클라이언트 | OpenAI, LangChain OpenAI | OpenAI 모델 호출, 구조화된 LLM 응답 생성 |
| LLM 모델 | GPT-4o 또는 그 이상 | 구조화 출력과 도구 호출 안정성이 필요한 고품질 생성 작업에 사용 |
| 데이터 검증 | Pydantic, Pydantic Settings | API 스키마, LLM 출력 파싱, 환경변수 설정 검증 |
| HTTP 클라이언트 | httpx, requests | Google Places API, callback, readiness check 등 외부 통신 |
| 장소 데이터 | Google Places API | 여행지 후보 검색, 장소 상세 정보 조회, 장소명 번역 보조 |

## 기술별 선택 근거

### Python 3.12

Python은 AI 및 데이터 처리 생태계가 풍부하고, LangGraph와 LangChain 계열 라이브러리의 기본 지원이 안정적입니다.
Python 3.12는 현재 레포의 `pyproject.toml`에서 요구하는 기준 버전이며, 최신 기능과 라이브러리 호환성 사이의 균형이 좋습니다.

> [!NOTE]
> 대안 검토
>
> | 대안 | 검토 내용 |
> | --- | --- |
> | Python 3.13 이상 | JIT 등 신규 기능을 사용할 수 있으나, 일부 AI/데이터 라이브러리 호환성을 추가 확인해야 합니다. |
> | Node.js, TypeScript | 기존 백엔드가 Node.js 기반인 경우 통합이 자연스러울 수 있으나, Python 기반 AI/데이터 라이브러리 활용성은 낮아질 수 있습니다. |

### FastAPI

FastAPI는 비동기 처리를 기본 지원하며, LLM 및 Google Places API처럼 외부 통신이 많은 AI 서비스에 적합합니다.
Pydantic과 자연스럽게 결합되므로 요청/응답 스키마를 명확하게 정의할 수 있습니다.

> [!NOTE]
> 대안 검토
>
> Flask는 단순한 API 서버에는 충분하지만, 비동기 처리와 타입 기반 스키마 검증을 기본 구조로 가져가기에는 FastAPI가 더 적합합니다.

### LangGraph

LangGraph는 상태 기반 그래프와 조건부 분기를 지원합니다.
Mohaeng-AI의 로드맵 생성, 의도 분석, 수정, 응답 생성 흐름처럼 여러 단계가 있고 실패 또는 상태에 따라 경로가 달라지는 작업에 적합합니다.

> [!NOTE]
> 대안 검토
>
> CrewAI는 역할 기반 에이전트 구성에 강점이 있으나, 이 프로젝트의 현재 구조는 명시적인 상태 전이와 API 요청 단위의 워크플로우 제어가 더 중요합니다.

### OpenAI 모델

선정 기술 기준의 LLM 모델은 GPT-4o 또는 그 이상의 OpenAI 모델입니다.
복잡한 JSON Schema 준수, 구조화 출력, 외부 도구 호출 제어가 필요한 작업에서 안정성을 우선합니다.
모델은 `LLM_MODEL_NAME`, `LLM_MODEL_QUALITY`, `LLM_MODEL_SPEED`, `LLM_MODEL_COST` 설정을 통해 목적별로 교체할 수 있습니다.

> [!NOTE]
> 대안 검토
>
> Claude 계열 모델을 대안으로 검토할 수 있습니다. 다만 현재 구현은 OpenAI 및 LangChain OpenAI 클라이언트를 중심으로 구성되어 있어, 다른 LLM 공급자를 도입하려면 라우팅과 클라이언트 추상화 검토가 필요합니다.

### Google Places API

Google Places API는 전 세계 장소 데이터를 조회할 수 있고, Text Search를 통해 사용자의 자연어성 검색어를 장소 후보로 변환하는 데 유용합니다.
현재 구현에서는 API 키가 없는 경우 Google Places 기능을 비활성화하거나 건너뛰는 구조를 사용합니다.

> [!NOTE]
> 대안 검토
>
> Naver Places API는 국내 장소 품질이 중요한 경우 검토할 수 있습니다. 다만 해외 여행지 범위와 API 응답 구조를 함께 비교해야 합니다.

### Pydantic

Pydantic은 API 요청/응답 모델, 환경변수 설정, LLM 출력 파싱에 사용합니다.
LLM 응답이 시스템 규격과 맞지 않을 때 조기에 오류를 확인할 수 있어, 재시도나 fallback 정책과 결합하기 좋습니다.

> [!NOTE]
> 대안 검토
>
> Marshmallow를 대안으로 검토할 수 있습니다. 다만 현재 FastAPI와 Python 타입 힌트 기반 구조에서는 Pydantic이 더 자연스럽습니다.

## 후보 또는 보류 기술

원본 Notion 문서에는 일정 분할과 경로 최적화를 위한 기술 후보가 포함되어 있었습니다.
현재 레포 의존성에는 포함되어 있지 않으므로, 아래 항목은 적용된 기술이 아니라 향후 구현 후보로 분리합니다.

| 분류 | 후보 기술 | 대안 | 검토 목적 |
| --- | --- | --- | --- |
| 클러스터링 알고리즘 | Scikit-learn K-Means | SciPy Hierarchical Clustering | 위치 좌표 기반 일자별 방문 권역 분할 |
| 경로 최적화 | Google OR-Tools | PyVRP | TSP 기반 최단 거리 동선 산출 |

이 후보들을 실제로 도입할 때는 다음 사항을 추가로 검증해야 합니다.

- 여행 일정 생성 요구사항이 좌표 기반 자동 군집화를 필요로 하는지 확인합니다.
- Google Places 응답의 좌표 품질과 누락 케이스를 검증합니다.
- 경로 최적화가 단순 정렬보다 사용자 경험을 의미 있게 개선하는지 확인합니다.
- 의존성 추가 시 Python 3.12 호환성, 실행 시간, 테스트 전략을 함께 검토합니다.

# TODO

- Scikit-learn 또는 OR-Tools 도입 여부는 실제 일정 분할/동선 최적화 요구사항이 확정된 뒤 결정합니다.
- OpenAI 외 모델 공급자 도입이 필요해지면 LLM 라우터 추상화 범위를 별도 설계 문서로 정리합니다.
