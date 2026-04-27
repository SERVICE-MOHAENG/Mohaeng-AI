## 프로젝트 개요
- `mohaeng-ai`는 모행 서비스의 ai 기능을 담당하는 백엔드 레포지토리입니다.
- 모행 서비스란, 사용자가 여행 계획을 수립하는 과정에서 어려움을 겪는 문제를 해결하기 위해서, LLM을 이용한 여행 로드맵 생성, 채팅으로 생성된 로드맵을 수정하는 기능을 지원하는것이 핵심입니다.
- Python 3.12 기반의 FastAPI 서비스입니다.
- 주요 기능은 AI 채팅, 생성, 추천이며, 핵심 코드는 `app/`에 있습니다.
- 테스트는 `tests/`, 운영 보조 스크립트는 `tools/`에 둡니다.
- 주요 의존성은 OpenAI, FastAPI, Pydantic, HTTP 클라이언트이며, Google Places와 Discord 웹훅을 선택적으로 사용합니다.

## 빌드 및 테스트
- 의존성 설치는 `uv sync`를 우선 사용합니다. 없으면 프로젝트 표준 Python 환경을 사용합니다.
- 로컬 실행은 저장소 루트에서 `uvicorn app.main:app --reload`를 사용합니다.
- 테스트는 `pytest`를 실행합니다.
- 린트와 포맷은 각각 `ruff check .`, `ruff format .`을 사용합니다.
- 큰 변경 전에는 `pre-commit run --all-files`를 실행합니다.

## 코드 스타일
- Python 3.12을 대상으로 합니다.
- `pyproject.toml` 기준으로 120자 라인 길이, 큰따옴표, 4칸 들여쓰기를 따릅니다.
- import는 그룹별로 정리하고, `app`은 first-party 패키지로 취급합니다.
- 요청/응답 경계는 가능한 한 명시적인 함수와 Pydantic 모델로 작성합니다.

## 테스트 지침
- 동작 변경이 있으면 `tests/`에 테스트를 추가하거나 수정합니다.
- 기존 테스트는 API 동작, readiness, callback delivery, timeout policy, recommendation 흐름을 다룹니다.
- 설정값에 영향을 받는 코드는 기본값과 오버라이드된 환경변수 모두를 고려해 검증합니다.

## 보안 및 설정
- 실제 비밀값은 커밋하지 않습니다. 로컬에서는 `.env`를 사용하고, 기준값은 `.env.example`을 따릅니다.
- 필수 비밀값은 `OPENAI_API_KEY`, `SERVICE_SECRET`, `HMAC_SECRET`입니다.
- Discord 웹훅 URL은 HTTPS이고 Discord 도메인인지 검증해야 합니다.
- 요청 타임아웃, trusted host, CORS, 보안 헤더는 명확한 이유가 없으면 유지합니다.

## 작업 규칙
- 파일을 수정하기 전에 기존 변경 사항을 확인하고, 사용자 변경은 되돌리지 않습니다.
- 커밋은 작고 설명적으로 유지합니다.
- 하위 프로젝트가 생기면 해당 위치에 더 가까운 `AGENTS.md`를 추가해 로컬 지침을 둡니다.
