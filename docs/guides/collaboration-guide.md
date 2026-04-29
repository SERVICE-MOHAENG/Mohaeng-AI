---
title: "AI 개발팀 협업 가이드"
status: "approved"
author: "@iamb0ttle"
created_at: 2026-04-27
tags: [guides, collaboration, git, ai, devops]
ai_action: "editable"
---

# 요약

이 문서는 Mohaeng-AI 개발팀의 협업 규칙을 정의합니다.
AI 도구를 활용해 개발 속도를 높이되, 코드 품질과 보안 검증을 생략하지 않는 것을 원칙으로 합니다.

# 배경

Mohaeng-AI는 작은 팀이 빠르게 기능을 만들고 검증하는 방식으로 개발합니다.
복잡한 절차는 줄이되, AI가 생성한 코드가 시스템 품질을 낮추거나 보안 문제를 만들지 않도록 최소한의 공통 규칙을 둡니다.

# 본문

## 기본 원칙

> [!IMPORTANT]
> AI의 속도는 활용하되, AI가 만든 기술 부채는 그대로 쌓지 않습니다.

팀은 속도와 실용성을 우선합니다.
다만 AI가 작성한 코드도 사람이 작성한 코드와 동일하게 테스트, 린트, 리뷰, 보안 검증을 통과해야 합니다.

## 개발 환경

모든 팀원은 같은 개발 기준을 사용합니다.
환경 차이로 인한 재현 실패를 줄이기 위해 프로젝트 표준 도구를 우선합니다.

| 항목 | 기준 |
| --- | --- |
| 언어 | Python 3.12 이상 |
| 패키지 매니저 | uv |
| 의존성 잠금 파일 | `uv.lock`을 Git에 포함 |
| 린터/포매터 | Ruff |
| 권장 에디터 | Cursor 또는 VS Code |

개발 환경 준비는 저장소 루트에서 다음 명령을 기준으로 합니다.

```bash
uv sync
uv run pre-commit install
```

## 브랜치 전략

Mohaeng-AI는 단순한 GitHub Flow를 사용합니다.
`develop` 브랜치를 별도로 두지 않고, 모든 작업은 `main`에서 분기해 Pull Request로 병합합니다.

기본 원칙은 다음과 같습니다.

- `main` 브랜치에서 작업 브랜치를 생성합니다.
- `main` 브랜치에 직접 push하지 않습니다.
- 작은 수정도 Pull Request를 통해 병합합니다.
- PR은 CI와 리뷰를 통과한 뒤 병합합니다.

## 브랜치 네이밍

브랜치는 작업 성격을 드러내는 접두어를 사용합니다.

| 접두어 | 설명 | 예시 |
| --- | --- | --- |
| `feat/` | 새로운 기능, 문서 작성, 디자인 등 새 작업 | `feat/rag-pipeline`, `feat/readme-update` |
| `fix/` | 버그 수정, 오타 수정 등 기존 문제 수정 | `fix/login-error`, `fix/typo-prompt` |
| `chore/` | 빌드, 패키지, 환경 설정 등 개발 외 작업 | `chore/docker-setup`, `chore/init-ruff` |

브랜치 이름은 영어 소문자와 하이픈을 사용합니다.

```text
feat/user-login-api
```

다음과 같은 이름은 사용하지 않습니다.

```text
feat/UserLogin
feat/로그인기능
```

## 코드 품질 관리

AI 도구가 작성한 코드는 기계 검증과 사람 리뷰를 모두 거칩니다.
자동화 도구는 포맷, lint, 테스트처럼 반복 가능한 문제를 잡고, 리뷰어는 의도와 로직을 검증합니다.

로컬에서 큰 변경 전에는 다음 명령을 실행합니다.

```bash
uv run pre-commit run --all-files
```

현재 pre-commit은 다음 항목을 검사합니다.

- trailing whitespace
- end-of-file fixer
- YAML 형식
- 대용량 파일 추가 여부
- Ruff lint 자동 수정
- Ruff format

## 기능별 검증 체크리스트

변경 범위가 작더라도 관련 테스트를 우선 실행하고, 공통 영향이 있으면 전체 테스트를 실행합니다.

| 변경 영역 | 우선 실행할 테스트 |
| --- | --- |
| API 라우터, 인증, 앱 부팅 | `uv run pytest tests/test_main.py` |
| readiness, 환경변수 설정 | `uv run pytest tests/test_readiness.py` |
| callback URL 조립과 전송 | `uv run pytest tests/test_callback_url.py tests/test_callback_delivery.py` |
| 여행지 추천 | `uv run pytest tests/test_recommend_service.py` |
| 로드맵 채팅 스키마 | `uv run pytest tests/test_chat_schema.py` |
| 로드맵 생성 단순화 파이프라인 | `uv run pytest tests/test_roadmap_generation_simplified_pipeline.py` |
| timeout 정책 | `uv run pytest tests/test_timeout_policy.py` |
| LLM 라우터와 Discord 알림 | `uv run pytest tests/test_llm_router_webhooks.py tests/test_webhook_notification.py` |
| 넓은 코드 변경 | `uv run pytest` |

문서만 수정한 경우에도 링크, 경로, 코드 위치가 실제 파일과 맞는지 확인합니다.

## Pull Request와 코드 리뷰

PR에는 관련 이슈, 작업 내용, AI 활용 여부, 검증 방법을 명시합니다.
AI가 생성한 코드가 포함된 경우 PR 템플릿의 AI 생성 코드 항목을 체크합니다.

리뷰에서는 다음 항목을 확인합니다.

- AI가 작성한 로직이 의도대로 동작하는지 확인합니다.
- API Key, 토큰, 비밀값이 하드코딩되지 않았는지 확인합니다.
- 불필요한 주석, 디버그 로그, `print` 문이 남아 있지 않은지 확인합니다.
- 테스트 또는 수동 검증 방법이 PR에 기록되어 있는지 확인합니다.

## CI와 배포 협업

Pull Request가 열리면 GitHub Actions CI가 실행됩니다.
CI는 Python 3.12 환경에서 의존성을 설치하고 Ruff lint, Ruff format check, pytest를 실행합니다.

`main` 브랜치에 push되면 Docker 이미지를 빌드하고 Docker Hub로 publish하는 workflow가 실행됩니다.
배포 인프라는 DevOps 담당 영역이며, 이 레포의 책임은 테스트를 통과하는 애플리케이션 코드와 정상 빌드 가능한 Docker 이미지를 제공하는 것입니다.

## 현재 설정 기준

Ruff 설정은 `pyproject.toml`을 기준으로 합니다.

```toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "B"]
ignore = ["B008"]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

pre-commit 설정은 `.pre-commit-config.yaml`을 기준으로 합니다.

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=100000']

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.13
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

# 관련 문서

- [Mohaeng-AI 문서 맵](../index.md)
- [Git 커밋 컨벤션](git-commit-convention.md)
- [기술 스택](../architecture/technology-stack.md)

# TODO

- 브랜치 보호 규칙과 필수 리뷰 인원은 GitHub 저장소 설정 기준이 확정되면 이 문서에 반영합니다.
- DevOps 배포 책임 경계가 변경되면 CI/CD 섹션을 갱신합니다.
