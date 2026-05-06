---
title: "헬스체크 API"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [api, healthcheck, readiness, operations]
ai_action: "editable"
---

# 요약

Mohaeng-AI는 프로세스 생존 확인을 위한 `/livez`와 외부 의존성 준비 상태 확인을 위한 `/readyz`를 제공합니다.
두 API는 서비스 간 인증을 요구하지 않습니다.

# 배경

운영 환경에서는 프로세스가 살아 있는지와 실제 요청을 처리할 준비가 되었는지를 구분해야 합니다.
`/livez`는 애플리케이션 프로세스 생존 여부만 확인하고, `/readyz`는 OpenAI와 Google Places 의존성 상태를 확인합니다.

# 본문

## `GET /livez`

| 항목 | 내용 |
| --- | --- |
| Method | `GET` |
| Path | `/livez` |
| 인증 | 없음 |
| 성공 응답 | `200 OK` |

응답:

```json
{
  "status": "alive"
}
```

## `GET /readyz`

| 항목 | 내용 |
| --- | --- |
| Method | `GET` |
| Path | `/readyz` |
| 인증 | 없음 |
| 성공 응답 | `200 OK` |
| 준비 실패 응답 | `503 Service Unavailable` |

준비 완료 응답:

```json
{
  "status": "ready",
  "checks": {
    "openai": {
      "status": "ok",
      "ok": true,
      "required": true,
      "detail": "OpenAI API 연결 가능 (openai-proxy.dsmhs.kr:443)"
    },
    "google_places": {
      "status": "skip",
      "ok": true,
      "required": false,
      "detail": "GOOGLE_PLACES_API_KEY 미설정으로 Google Places 체크를 건너뜁니다."
    }
  }
}
```

준비 실패 응답:

```json
{
  "status": "not_ready",
  "checks": {
    "openai": {
      "status": "fail",
      "ok": false,
      "required": true,
      "detail": "OPENAI_API_KEY가 설정되지 않았습니다."
    },
    "google_places": {
      "status": "skip",
      "ok": true,
      "required": false,
      "detail": "GOOGLE_PLACES_API_KEY 미설정으로 Google Places 체크를 건너뜁니다."
    }
  }
}
```

## Readiness 기준

| 체크 | 필수 여부 | 설명 |
| --- | --- | --- |
| `openai` | 필수 | `OPENAI_API_KEY` 설정과 `OPENAI_BASE_URL` 호스트(`openai-proxy.dsmhs.kr:443`) TCP 연결 가능 여부 |
| `google_places` | 선택 | `GOOGLE_PLACES_API_KEY`가 있을 때 `places.googleapis.com:443` TCP 연결 가능 여부 |

## 구현 위치

| 구분 | 위치 |
| --- | --- |
| FastAPI 앱과 라우팅 | `app/main.py` |
| readiness 체크 | `app/core/readiness.py` |
| 환경변수 설정 | `app/core/config.py` |
| 테스트 | `tests/test_main.py`, `tests/test_readiness.py` |

# 관련 문서

- [기술 스택](../architecture/technology-stack.md)
- [AI 개발팀 협업 가이드](../guides/collaboration-guide.md)

# TODO

- 배포 플랫폼의 liveness/readiness probe 설정이 확정되면 권장 probe 주기를 문서화합니다.
