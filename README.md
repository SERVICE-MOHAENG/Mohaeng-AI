# Mohaeng AI

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Service-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/Status-Product%20Iteration-2F80ED)](https://github.com/SERVICE-MOHAENG/Mohaeng-AI)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](./LICENSE.md)

<img style="margin: 0 auto" width="595" height="842" alt="모행판넬" src="https://github.com/user-attachments/assets/ace8d49b-d3d4-46ce-8d58-f18bae970908" />

<br/>

Mohaeng AI는 사용자의 취향과 여행 조건을 바탕으로 여행 로드맵을 만들고, 대화로 일정을 자연스럽게 수정할 수 있게 돕는 AI 여행 플래너입니다.

여행 계획을 처음부터 직접 짜는 부담을 줄이고, 사용자가 원하는 분위기와 제약 조건에 맞는 장소와 동선을 빠르게 제안하는 것을 목표로 합니다.

## Product Vision

여행 계획은 검색, 비교, 거리 계산, 일정 조율이 반복되는 작업입니다. Mohaeng AI는 이 과정을 하나의 흐름으로 묶어, 사용자가 “어디를 갈지”보다 “어떤 여행을 하고 싶은지”에 집중할 수 있게 만듭니다.

## Core Experience

- 사용자는 설문이나 요청을 통해 여행 조건을 입력합니다.
- AI는 조건에 맞는 여행 로드맵을 생성합니다.
- 생성된 로드맵은 장소, 일정, 이동 흐름을 포함합니다.
- 사용자는 채팅으로 “카페를 더 넣어줘”, “너무 빡빡해”, “비 오는 날 기준으로 바꿔줘”처럼 자연어 수정을 요청할 수 있습니다.
- 추천 흐름은 사용자의 취향과 상황을 반영해 더 적합한 후보를 제안합니다.

## Key Features

### 여행 로드맵 생성

사용자의 여행 조건을 기반으로 하루 또는 여러 날의 여행 일정을 생성합니다. 장소 추천뿐 아니라 방문 순서와 일정 흐름까지 고려합니다.

### 대화형 일정 수정

이미 생성된 로드맵을 채팅으로 수정할 수 있습니다. 사용자는 복잡한 편집 UI 없이 자연어로 일정을 조정할 수 있습니다.

### 설문 기반 추천

사용자의 선호도, 여행 목적, 동행 유형, 분위기 등을 바탕으로 더 적합한 여행 후보를 추천합니다.

### 장소 품질 보정

외부 장소 데이터와 AI 판단을 함께 사용해 후보 장소의 적합도를 높입니다. 필요에 따라 장소 후보를 재정렬하고, 여행 맥락에 맞는 선택을 돕습니다.

### 비동기 처리와 콜백

AI 생성 작업은 시간이 걸릴 수 있으므로 요청을 먼저 접수하고, 완료된 결과를 콜백으로 전달하는 흐름을 사용합니다. 사용자는 긴 응답을 기다리지 않고 다음 단계로 넘어갈 수 있습니다.

## Target Users

- 여행 계획을 직접 짜기 번거로운 사용자
- 취향에 맞는 장소를 빠르게 추천받고 싶은 사용자
- 이미 만든 일정을 자연어로 쉽게 수정하고 싶은 사용자
- 데이트, 가족 여행, 친구 여행처럼 목적이 뚜렷한 코스를 찾는 사용자

## Product Principles

- 사용자의 입력 부담을 줄입니다.
- 장소 나열보다 실제 여행 가능한 동선을 우선합니다.
- 추천 이유와 일정 흐름이 납득 가능해야 합니다.
- AI 결과는 한 번에 끝나는 답변이 아니라, 대화를 통해 계속 개선되는 초안이어야 합니다.
- 운영 피드백을 기반으로 추천 품질과 제약 조건을 점진적으로 강화합니다.

## Current Focus

- 안정적인 로드맵 생성 품질 확보
- LLM 응답 시간과 타임아웃 개선
- 하루 일정에 포함할 적정 장소 수 기준 정리
- 장소 유형 정보를 응답에 포함할지 결정
- 운영 환경에서 장소 유형 필터의 실제 만족도 검증

## TODO

- [x] Discord Webhook 추가
- [ ] LLM 타임아웃 문제 해결
- [ ] 로드맵 생성 시 하루 최대 장소 수 제한 검토
- [ ] 로드맵 생성 및 수정 응답값에 장소 유형 포함 여부 결정
- [ ] 장소 유형 필터만 적용하는 방식은 추후 운영 피드백을 보고 검토

## Contributors

Mohaeng AI는 SERVICE-MOHAENG 팀이 함께 만들어가고 있습니다.

|  | Profile Link |
| --- | --- |
| [<img src="https://avatars.githubusercontent.com/u/189304119?v=4" width="80" alt="iamb0ttle avatar">](https://github.com/iamb0ttle) | [@iamb0ttle](https://github.com/iamb0ttle) |
| [<img src="https://avatars.githubusercontent.com/u/248457480?v=4" width="80" alt="zweadfx avatar">](https://github.com/zweadfx) | [@zweadfx](https://github.com/zweadfx) |
